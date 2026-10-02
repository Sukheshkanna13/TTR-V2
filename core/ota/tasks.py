"""
ARI outbox worker (C4 — certification pre-flight P2 + P3, Test 12).

``process_ari_outbox`` runs every minute (registered in ``rooms/apps.py``):

1. **Claim** due rows (``pending`` and ``next_retry_at <= now``) under
   ``SELECT … FOR UPDATE SKIP LOCKED`` and push their ``next_retry_at`` forward
   by a lease. A second worker running at the same time skips them, and if this
   worker dies mid-run the lease simply expires and the rows are retried.
2. **Coalesce** per property: every pending availability row for a property —
   any room type, any dates — becomes ONE ``/availability`` call. Date ranges
   are merged, clipped to [today, today + horizon), and values are always
   computed from the current database state, so merging is lossless.
3. **Rate-limit**: at most ``CHANNEX_OUTBOX_MAX_CALLS_PER_RUN`` calls (default
   18, under Channex's 20/min) and at most one call per property per message
   type per run. Rows over the budget are released untouched for the next run.
4. **Retry**: 429 / 5xx / network errors back off exponentially
   (30s, 60s, 120s … capped at 1h, honouring Retry-After) up to
   ``CHANNEX_OUTBOX_MAX_RETRIES``; then ``failed``. Other 4xx → ``failed`` at
   once. A missing API key pauses the run without spending any retries.

Only change types with a value builder are claimed (``SUPPORTED_CHANGE_TYPES``).
Rates and restrictions rows stay ``pending`` until their builders exist
(blocked on decision D5 and the C5 restriction fields); they are never dropped.
"""

from __future__ import annotations

import logging
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.ota.availability import compute_per_date_availability
from core.ota.channex import ChannexAPIError, ChannexConfigError, ChannexManager
from core.ota.mapping import resolve_room_type
from core.ota.models import ARIChange, ChannexProperty

logger = logging.getLogger(__name__)

# Change types the worker can currently build values for. Add "rates" /
# "restrictions" here once their per-date builders land (D5, C5).
SUPPORTED_CHANGE_TYPES = (ARIChange.CHANGE_AVAILABILITY,)

_DEFAULTS = {
    "MAX_CALLS_PER_RUN": 18,     # Channex allows 20 ARI calls/min; keep headroom
    "MAX_RETRIES": 8,            # 30s → 1h backoff ladder, ~2h total
    "BACKOFF_BASE_SECONDS": 30,
    "BACKOFF_CAP_SECONDS": 3600,
    "LEASE_SECONDS": 300,        # crash recovery window for claimed rows
    "RUN_TIME_BUDGET_SECONDS": 40,  # stay well inside Q_CLUSTER timeout (60s)
    "CLAIM_LIMIT": 2000,
    "HORIZON_DAYS": 500,         # Channex ARI window
}


def _cfg(name: str) -> int:
    return int(getattr(settings, f"CHANNEX_OUTBOX_{name}", _DEFAULTS[name]))


def _get_client() -> ChannexManager:
    return ChannexManager()


# ---------------------------------------------------------------------------
# Row state transitions (all set updated_at explicitly: .update() skips auto_now)
# ---------------------------------------------------------------------------

def _ids(rows):
    return [r.id for r in rows]


def _mark_sent(rows, task_id: str = "", note: str = "") -> None:
    now = timezone.now()
    ARIChange.objects.filter(id__in=_ids(rows)).update(
        status=ARIChange.STATUS_SENT, channex_task_id=task_id[:100],
        error_detail=note, next_retry_at=now, updated_at=now,
    )


def _mark_failed(rows, detail: str) -> None:
    now = timezone.now()
    ARIChange.objects.filter(id__in=_ids(rows)).update(
        status=ARIChange.STATUS_FAILED, error_detail=detail[:5000], updated_at=now,
    )


def _release(rows, delay_seconds: int = 0, note: str | None = None) -> None:
    """Hand rows back to the queue without counting an attempt."""
    now = timezone.now()
    fields = {"next_retry_at": now + timedelta(seconds=delay_seconds), "updated_at": now}
    if note is not None:
        fields["error_detail"] = note[:5000]
    ARIChange.objects.filter(id__in=_ids(rows), status=ARIChange.STATUS_PENDING).update(**fields)


def _backoff_seconds(attempt: int, retry_after: int | None = None) -> int:
    delay = min(_cfg("BACKOFF_CAP_SECONDS"), _cfg("BACKOFF_BASE_SECONDS") * 2 ** (attempt - 1))
    if retry_after:
        delay = max(delay, retry_after)
    return delay


def _schedule_retry(rows, error: str, retry_after: int | None = None) -> str:
    """Count an attempt; back off, or give up after MAX_RETRIES. Returns outcome."""
    attempt = max(r.retry_count for r in rows) + 1
    if attempt > _cfg("MAX_RETRIES"):
        _mark_failed(rows, f"Gave up after {attempt} attempts. Last error: {error}")
        return "failed"
    now = timezone.now()
    ARIChange.objects.filter(id__in=_ids(rows)).update(
        status=ARIChange.STATUS_PENDING,
        retry_count=attempt,
        next_retry_at=now + timedelta(seconds=_backoff_seconds(attempt, retry_after)),
        error_detail=f"Attempt {attempt} failed: {error}"[:5000],
        updated_at=now,
    )
    return "retry"


# ---------------------------------------------------------------------------
# Value building
# ---------------------------------------------------------------------------

def _merge_ranges(ranges):
    """Merge [start, end) ranges that overlap or touch; drop empty ones."""
    merged = []
    for start, end in sorted(r for r in ranges if r[1] > r[0]):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _compress(date_counts: dict, base: dict, field: str) -> list:
    """Collapse consecutive dates with the same value into one inclusive range."""
    values = []
    for day_str in sorted(date_counts):
        day = date.fromisoformat(day_str)
        value = date_counts[day_str]
        last = values[-1] if values else None
        if (
            last is not None
            and last[field] == value
            and date.fromisoformat(last["date_to"]) + timedelta(days=1) == day
        ):
            last["date_to"] = day_str
        else:
            values.append({**base, "date_from": day_str, "date_to": day_str, field: value})
    return values


def _build_availability(mapping: ChannexProperty, rows, today: date, horizon_end: date):
    """Return (values, rows_in_call, rows_nothing_to_push, rows_unmapped)."""
    by_type = defaultdict(list)
    for row in rows:
        by_type[row.room_type].append(row)

    values, in_call, nothing, unmapped = [], [], [], []
    for room_type, type_rows in by_type.items():
        ranges = _merge_ranges(
            (max(r.date_from, today), min(r.date_to, horizon_end)) for r in type_rows
        )
        if not ranges:
            nothing.extend(type_rows)
            continue
        room_type_uuid = resolve_room_type(mapping.property_id, room_type)
        if room_type_uuid is None:
            unmapped.extend(type_rows)
            continue
        base = {
            "property_id": str(mapping.channex_property_id),
            "room_type_id": room_type_uuid,
        }
        for start, end in ranges:
            counts = compute_per_date_availability(room_type, mapping.property_id, start, end)
            values.extend(_compress(counts, base, "availability"))
        in_call.extend(type_rows)
    return values, in_call, nothing, unmapped


# ---------------------------------------------------------------------------
# Claim + run
# ---------------------------------------------------------------------------

def _claim_rows(now) -> list:
    active_ids = list(ChannexProperty.objects.filter(is_active=True).values_list("id", flat=True))
    if not active_ids:
        return []
    with transaction.atomic():
        rows = list(
            ARIChange.objects.select_for_update(skip_locked=True)
            .filter(
                status=ARIChange.STATUS_PENDING,
                next_retry_at__lte=now,
                property_mapping_id__in=active_ids,
                change_type__in=SUPPORTED_CHANGE_TYPES,
            )
            .order_by("created_at")[: _cfg("CLAIM_LIMIT")]
        )
        if rows:
            ARIChange.objects.filter(id__in=_ids(rows)).update(
                next_retry_at=now + timedelta(seconds=_cfg("LEASE_SECONDS")),
                updated_at=now,
            )
    return rows


def process_ari_outbox() -> dict:
    """Scheduled every minute. Returns a summary dict (visible in django-q)."""
    started = time.monotonic()
    now = timezone.now()
    today = timezone.localdate()
    horizon_end = today + timedelta(days=_cfg("HORIZON_DAYS"))
    summary = Counter()

    rows = _claim_rows(now)
    summary["claimed"] = len(rows)
    if not rows:
        return dict(summary)

    unresolved = {r.id: r for r in rows}  # anything left here is released at the end

    def settle(group):
        for r in group:
            unresolved.pop(r.id, None)

    by_property = defaultdict(list)
    for row in rows:  # rows are oldest-first, so properties are served oldest-first
        by_property[row.property_mapping_id].append(row)
    mappings = ChannexProperty.objects.in_bulk(list(by_property))

    try:
        client = _get_client()
        for mapping_id, property_rows in by_property.items():
            mapping = mappings.get(mapping_id)
            if mapping is None:  # deleted mid-run; its rows cascade away
                settle(property_rows)
                continue
            # One message type today; rates/restrictions become a second
            # /restrictions call per property here once their builders land.
            group = [r for r in property_rows if r.change_type == ARIChange.CHANGE_AVAILABILITY]
            if not group:
                continue

            if summary["calls"] >= _cfg("MAX_CALLS_PER_RUN") or (
                time.monotonic() - started > _cfg("RUN_TIME_BUDGET_SECONDS")
            ):
                summary["deferred"] += len(group)
                continue  # left in `unresolved`, released for the next run

            try:
                values, in_call, nothing, unmapped = _build_availability(
                    mapping, group, today, horizon_end,
                )
            except Exception as exc:  # DB hiccup etc. — retry later, never drop
                logger.exception("Building availability failed for %s", mapping)
                outcome = _schedule_retry(group, f"{type(exc).__name__}: {exc}")
                summary[outcome] += len(group)
                settle(group)
                continue

            if nothing:
                _mark_sent(nothing, note="Skipped: no dates inside the push window.")
                summary["skipped"] += len(nothing)
                settle(nothing)
            if unmapped:
                missing = sorted({r.room_type for r in unmapped})
                _mark_failed(unmapped, f"No Channex room-type mapping for {missing}. "
                                       "Add it in admin, then requeue.")
                summary["failed"] += len(unmapped)
                settle(unmapped)
            if not in_call:
                continue

            summary["calls"] += 1
            try:
                task_id = client.push_availability_values(values)
            except ChannexConfigError:
                raise
            except ChannexAPIError as exc:
                if exc.retryable:
                    outcome = _schedule_retry(in_call, str(exc), exc.retry_after)
                else:
                    _mark_failed(in_call, str(exc))
                    outcome = "failed"
                logger.warning("Channex availability push for %s: %s (%s)", mapping, exc, outcome)
                summary[outcome] += len(in_call)
                settle(in_call)
                continue
            except Exception as exc:
                logger.exception("Unexpected error pushing availability for %s", mapping)
                outcome = _schedule_retry(in_call, f"{type(exc).__name__}: {exc}")
                summary[outcome] += len(in_call)
                settle(in_call)
                continue

            _mark_sent(in_call, task_id=task_id)
            summary["sent"] += len(in_call)
            settle(in_call)

    except ChannexConfigError as exc:
        logger.error("ARI outbox paused: %s", exc)
        summary["paused"] += len(unresolved)
        _release(list(unresolved.values()), note=f"Paused: {exc}")
        unresolved.clear()
    finally:
        if unresolved:
            _release(list(unresolved.values()))

    result = dict(summary)
    logger.info("ARI outbox run: %s", result)
    return result


# ---------------------------------------------------------------------------
# C8 — Full sync (certification Test 1 + nightly reconciliation)
# ---------------------------------------------------------------------------

def full_sync_property(property_id) -> dict:
    """Push 500 days of availability + rates/restrictions for one property.

    Channex certification Test 1 requires:
      - All availability for all room types across 500 days → 1 API call
      - All rates/restrictions for all rate plans across 500 days → 1 API call

    This function makes exactly those 2 calls.  It is intentionally separate
    from the outbox worker — it bypasses the outbox and pushes directly so
    the cert screenshare can show a clean "full sync fired, 2 calls made"
    sequence.

    Returns a dict with keys: property, availability_task_id,
    restrictions_task_id, room_types, rate_plans, errors.

    Safe to call manually via ``python manage.py channex_full_sync``
    or from the nightly schedule.  Raises nothing — errors are returned
    in the ``errors`` list so the caller can log/report them.
    """
    from datetime import date, timedelta
    from core.ota.models import ChannexProperty, ChannexRoomType, ChannexRatePlan
    from core.ota.availability import compute_per_date_availability
    from core.ota.channex import ChannexManager, ChannexAPIError, ChannexConfigError

    result = {
        "property_id": str(property_id),
        "availability_task_id": "",
        "restrictions_task_id": "",
        "room_types": [],
        "rate_plans": [],
        "errors": [],
    }

    # ── Resolve mapping ──────────────────────────────────────────────────────
    try:
        mapping = ChannexProperty.objects.select_related("property").get(
            property_id=property_id, is_active=True,
        )
    except ChannexProperty.DoesNotExist:
        result["errors"].append(f"No active Channex mapping for property {property_id}.")
        logger.error("full_sync: %s", result["errors"][-1])
        return result

    today = date.today()
    horizon_end = today + timedelta(days=_cfg("HORIZON_DAYS"))
    property_uuid = str(mapping.channex_property_id)
    currency = mapping.currency

    client = ChannexManager()

    # ── Build availability values (1 entry per room-type per night) ──────────
    availability_values = []
    room_type_mappings = list(
        ChannexRoomType.objects.filter(
            property_mapping=mapping,
        ).select_related("property_mapping")
    )

    for rt_mapping in room_type_mappings:
        room_type = rt_mapping.room_type
        room_type_uuid = str(rt_mapping.channex_room_type_id)
        result["room_types"].append(room_type)

        counts = compute_per_date_availability(room_type, property_id, today, horizon_end)
        if not counts:
            logger.warning("full_sync: no availability data for %s at property %s", room_type, property_id)
            continue

        # _compress builds date-range entries from the per-date dict
        base = {"property_id": property_uuid, "room_type_id": room_type_uuid}
        availability_values.extend(_compress(counts, base, "availability"))

    # ── Build rates/restrictions values (1 entry per rate-plan per night) ────
    restrictions_values = []
    rate_plan_mappings = list(
        ChannexRatePlan.objects.filter(
            room_type_mapping__property_mapping=mapping,
        ).select_related("room_type_mapping__property_mapping")
    )

    for rp_mapping in rate_plan_mappings:
        rate_plan_uuid = str(rp_mapping.channex_rate_plan_id)
        room_type = rp_mapping.room_type_mapping.room_type
        result["rate_plans"].append(rp_mapping.name)

        # Build one entry per night covering the full horizon.
        # Rate: look up RoomRate override for that date; fall back to
        # Room.price_per_night for the room type at this property.
        # Restrictions: read from RoomRate if a row covers that date.
        from rooms.models import Room, RoomRate
        from django.db.models import Q

        # Get base price (cheapest active room of this type — representative
        # price for the type; matches the "decide which room's price represents
        # the type" decision from D5 in the gap analysis).
        base_room = (
            Room.objects.filter(
                property_id=property_id,
                room_type=room_type,
                is_active=True,
            )
            .order_by("price_per_night")
            .first()
        )
        if base_room is None:
            logger.warning("full_sync: no active room of type %s at property %s", room_type, property_id)
            continue

        # Fetch all RoomRate overrides for this room in the horizon
        rate_overrides = list(
            RoomRate.objects.filter(
                room=base_room,
                start_date__lt=horizon_end,
                end_date__gte=today,
            ).order_by("start_date")
        )

        # Build per-date map: date → (price, restrictions)
        from datetime import timedelta as td

        def _nights_list(s, e):
            d, out = s, []
            while d < e:
                out.append(d)
                d += td(days=1)
            return out

        nightly = {}
        for night in _nights_list(today, horizon_end):
            price = base_room.price_per_night
            min_stay_arrival = None
            min_stay_through = None
            max_stay = None
            stop_sell = False
            closed_to_arrival = False
            closed_to_departure = False
            for override in rate_overrides:
                if override.start_date <= night < override.end_date:
                    price = override.price
                    if override.min_stay_arrival is not None:
                        min_stay_arrival = override.min_stay_arrival
                    if override.min_stay_through is not None:
                        min_stay_through = override.min_stay_through
                    if override.max_stay is not None:
                        max_stay = override.max_stay
                    stop_sell = override.stop_sell
                    closed_to_arrival = override.closed_to_arrival
                    closed_to_departure = override.closed_to_departure
                    break
            nightly[night] = {
                "price": price,
                "min_stay_arrival": min_stay_arrival,
                "min_stay_through": min_stay_through,
                "max_stay": max_stay,
                "stop_sell": stop_sell,
                "closed_to_arrival": closed_to_arrival,
                "closed_to_departure": closed_to_departure,
            }

        # Compress into date-range entries (consecutive identical nights → 1 row)
        if not nightly:
            continue

        nights_list = sorted(nightly.keys())
        range_start = nights_list[0]
        prev = nightly[range_start]
        for night in nights_list[1:]:
            cur = nightly[night]
            if cur != prev:
                entry = {
                    "property_id": property_uuid,
                    "rate_plan_id": rate_plan_uuid,
                    "date_from": range_start.isoformat(),
                    "date_to": night.isoformat(),  # exclusive end
                    "rate": str(prev["price"]),
                }
                for field in ("min_stay_arrival", "min_stay_through", "max_stay"):
                    if prev[field] is not None:
                        entry[field] = prev[field]
                for field in ("stop_sell", "closed_to_arrival", "closed_to_departure"):
                    if prev[field]:
                        entry[field] = True
                restrictions_values.append(entry)
                range_start = night
                prev = cur
        # Final range
        entry = {
            "property_id": property_uuid,
            "rate_plan_id": rate_plan_uuid,
            "date_from": range_start.isoformat(),
            "date_to": horizon_end.isoformat(),
            "rate": str(prev["price"]),
        }
        for field in ("min_stay_arrival", "min_stay_through", "max_stay"):
            if prev[field] is not None:
                entry[field] = prev[field]
        for field in ("stop_sell", "closed_to_arrival", "closed_to_departure"):
            if prev[field]:
                entry[field] = True
        restrictions_values.append(entry)

    # ── Push ─────────────────────────────────────────────────────────────────
    try:
        if availability_values:
            result["availability_task_id"] = client.push_availability_values(availability_values)
            logger.info("full_sync: availability pushed for property %s, task_id=%s",
                        property_id, result["availability_task_id"])
        else:
            result["errors"].append("No availability values built — check room type mappings.")

        if restrictions_values:
            result["restrictions_task_id"] = client.push_restriction_values(restrictions_values)
            logger.info("full_sync: rates/restrictions pushed for property %s, task_id=%s",
                        property_id, result["restrictions_task_id"])
        else:
            result["errors"].append("No rates/restrictions values built — check rate plan mappings.")

    except ChannexConfigError as exc:
        result["errors"].append(f"Config error: {exc}")
        logger.error("full_sync aborted for property %s: %s", property_id, exc)
    except ChannexAPIError as exc:
        result["errors"].append(f"API error {exc.status_code}: {exc}")
        logger.error("full_sync API error for property %s: %s", property_id, exc)
    except Exception as exc:
        result["errors"].append(f"Unexpected error: {exc}")
        logger.exception("full_sync unexpected error for property %s", property_id)

    return result


def nightly_full_sync() -> dict:
    """Run full_sync_property for every active Channex property.

    Scheduled once per day (off-peak).  Channex cert rule: full sync ≤ once
    per 24 h and must not replace delta updates.  This is a reconciliation
    safety-net only — the outbox handles real-time deltas.
    """
    from core.ota.models import ChannexProperty

    results = {}
    for mapping in ChannexProperty.objects.filter(is_active=True).select_related("property"):
        logger.info("nightly_full_sync: starting for property %s", mapping.property_id)
        results[str(mapping.property_id)] = full_sync_property(mapping.property_id)
    logger.info("nightly_full_sync: done. properties=%d", len(results))
    return results
