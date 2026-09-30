"""
Outbound entry point (contract §3.1).

Every code path that changes availability, rates or restrictions calls
``record_ari_change``. It only writes ``ARIChange`` outbox rows; the scheduled
worker ``core.ota.tasks.process_ari_outbox`` coalesces and pushes them.
Never call the Channex API directly from a view or service.

Because rows are written with the caller's database connection, they commit or
roll back together with the business change that caused them (a true outbox).
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from django.utils.dateparse import parse_date

from core.ota.mapping import resolve_property_mapping
from core.ota.models import ARIChange

logger = logging.getLogger(__name__)

VALID_CHANGE_TYPES = frozenset(choice for choice, _ in ARIChange.CHANGE_TYPE_CHOICES)


def _coerce_date(value, name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed = parse_date(value)
        if parsed is not None:
            return parsed
    raise ValueError(f"record_ari_change: {name} must be a date or YYYY-MM-DD string, got {value!r}")


def record_ari_change(
    room_type: str,
    property_id,
    date_from,
    date_to,
    change_types=("availability",),
) -> None:
    """Record that ARI changed for ``room_type`` at ``property_id``.

    ``date_to`` is exclusive (a one-night change on 1 Oct is 1 Oct → 2 Oct).
    ``change_types`` is any subset of {"availability", "rates", "restrictions"}.

    No-ops (with a log line) when the property has no active Channex mapping or
    the range is empty. Raises ``ValueError`` for programming errors (unknown
    change type, unparseable date) so bad hooks fail loudly in tests.
    """
    if isinstance(change_types, str):
        change_types = (change_types,)
    types = list(dict.fromkeys(change_types))  # de-dupe, keep order
    unknown = set(types) - VALID_CHANGE_TYPES
    if unknown or not types:
        raise ValueError(f"record_ari_change: invalid change_types {change_types!r}")

    start = _coerce_date(date_from, "date_from")
    end = _coerce_date(date_to, "date_to")

    if not room_type or property_id is None:
        logger.warning(
            "record_ari_change skipped: room_type=%r property_id=%r", room_type, property_id,
        )
        return
    if end <= start:
        logger.warning(
            "record_ari_change skipped empty range %s..%s (date_to is exclusive)", start, end,
        )
        return

    mapping = resolve_property_mapping(property_id)
    if mapping is None:
        logger.debug("record_ari_change: property %s not connected to Channex; no-op", property_id)
        return

    ARIChange.objects.bulk_create([
        ARIChange(
            property_mapping=mapping,
            change_type=change_type,
            room_type=room_type,
            date_from=start,
            date_to=end,
        )
        for change_type in types
    ])
    logger.info(
        "Recorded ARI change %s for %s at property %s, %s..%s",
        "+".join(types), room_type, property_id, start, end,
    )
