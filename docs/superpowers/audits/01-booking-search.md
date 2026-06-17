# Booking / Search / Hold / Pricing — Data-Flow Audit

Scope: `rooms/models.py`, `rooms/views.py`, `rooms/serializers.py`, `rooms/tasks.py`, `rooms/urls.py`.
Read-only audit. Focus: state transitions, concurrency, date/availability math, money/Decimal, param plumbing, serializer/model/view contracts, error swallowing, validation.

## Summary

| ID | Severity | Title | Location |
|----|----------|-------|----------|
| BSF-01 | Critical | `auto_complete_bookings` writes dead status literal `"needs_cleaning"` — room never returns to bookable | rooms/tasks.py:41 |
| BSF-02 | Critical | Tax computed but never charged or added to total — guest pays pre-tax amount, books show wrong total | rooms/models.py:477-491 + payments flow |
| BSF-03 | High | `calculate_price` returns a bare `int` when no nights / mixes `int` + `Decimal`; daily rate built with inclusive `end_date` | rooms/models.py:216-244 |
| BSF-04 | High | Dev `ProcessPaymentView` confirms with no row lock / no overlap re-check — double-confirm race | rooms/views.py:464-510 |
| BSF-05 | High | Search availability is check-then-act with no lock; stale-hold rooms reappear but no guard before hold create on the search path | rooms/views.py:56-87, 155-164 |
| BSF-06 | Medium | `compute_tax` swallows all exceptions to `0.00`, silently hiding GST-config and arithmetic errors | rooms/models.py:477-491 |
| BSF-07 | Medium | `release_expired_holds` task uses `<` while `is_hold_expired` uses `>=` — one-tick disagreement between task and request-path expiry | rooms/tasks.py:14-17 vs models.py:398 |
| BSF-08 | Medium | Hold price/availability re-check missing on confirm: price frozen at hold time, never re-validated against RoomRate changes | rooms/views.py:307-308, payments verify |
| BSF-09 | Medium | `SearchSerializer` has no upper bound / cross-check on `min_price` vs `max_price`; inverted range silently returns empty | rooms/serializers.py:129-138 |
| BSF-10 | Low | `BookingSerializer` rewrites `pending`→`HELD` in output but every view/state check compares the raw `pending` literal — representation/contract split | rooms/serializers.py:244-262 |
| BSF-11 | Low | `MyBookingsView` auto-expire loops per-row (`save()` each) instead of using the bulk task; N queries and races with the bulk task | rooms/views.py:737-738 |
| BSF-12 | Low | `CalendarView` reads `is_hold_expired` but query also returns already-expired-by-clock pending holds as "HELD" events | rooms/views.py:806-839 |

---

## BSF-01 — Auto-complete sets a non-existent room status, bricking the room
- Severity: Critical
- Location: `rooms/tasks.py:41`
- Offending code:
  ```python
  room.operational_status = "needs_cleaning"
  room.save(update_fields=["operational_status"])
  ```
- Data flow: `auto_complete_bookings()` runs on the qcluster worker, finds CONFIRMED bookings past checkout, and sets the room's `operational_status` to `"needs_cleaning"` before marking the booking COMPLETED.
- Why it's a bug: `Room.OPERATIONAL_STATUS_CHOICES` defines only `available / cleaning / maintenance / out_of_order` (`models.py:171-181`). Migration `0012_room_operational_status_expand.py` explicitly **renamed** `needs_cleaning` → `cleaning`. The string `"needs_cleaning"` is now a dead literal. Search (`views.py:160`, `operational_status="available"`) and hold (`views.py:292`) only accept rooms whose status is `"available"`. A room written to `"needs_cleaning"` matches no choice and no available filter.
- Impact: Every room that completes a stay is moved into a status that (a) is invalid per the model's choices and (b) is never `"available"`, so it permanently disappears from search and can never be held/booked again until an admin manually fixes it. This silently shrinks bookable inventory every night the worker runs.

## BSF-02 — GST is computed but never charged, and the stored/displayed total excludes it
- Severity: Critical
- Location: `rooms/models.py:477-491` (`compute_tax`), with `rooms/views.py:307-308` and the payments confirm path (`payments/views.py:234-240`).
- Offending code (model):
  ```python
  self.tax_amount = (self.total_price * rate / Decimal('100')).quantize(Decimal('0.01'))
  ...
  self.save(update_fields=["tax_amount"])
  ```
- Data flow: At hold time `total_price = room.calculate_price(...)` (no tax). The Razorpay order is created for `amount_inr=booking.total_price` (`views.py:419`) / `int(booking.total_price * 100)` paise (`views.py:413`). On payment verify, `compute_tax()` is called (`payments/views.py:240`) which writes `tax_amount` to a column — but nothing ever adds `tax_amount` to `total_price`, and the charge already happened at the pre-tax amount. `ConfirmationView` then reports `"total_paid": str(booking.total_price)` (`views.py:715`) — still pre-tax.
- Why it's a bug: `tax_amount` is a write-only sink. The amount the guest is actually charged, the amount stored as the booking total, and the amount shown on the confirmation all exclude GST. The tax number exists only in its own column, disconnected from money movement.
- Impact: Revenue/accounting mismatch on every booking — GST is recorded as owed but never collected; invoices and confirmations understate the true total. Either the platform under-charges tax on every stay or the displayed/charged totals are inconsistent with the tax ledger.

## BSF-03 — `calculate_price` type inconsistency + inclusive end_date in the rate map
- Severity: High
- Location: `rooms/models.py:216-244`
- Offending code:
  ```python
  rate_lookup = {}
  for r in rates:
      current = r.start_date
      while current <= r.end_date:        # inclusive end_date
          rate_lookup[current] = r.price
          current += timedelta(days=1)
  total_price = 0                          # int seed
  current_date = check_in
  while current_date < check_out:
      daily_price = rate_lookup.get(current_date, self.price_per_night)
      total_price += daily_price           # int + Decimal mixing
      return total_price
  ```
- Data flow: Search (`views.py:308`, serializer `get_dynamic_total_price`) and hold both call this to produce the money the guest is charged.
- Why it's a bug:
  1. `total_price` is seeded as Python `int 0`. If a booking somehow has `check_out == check_in` (the model CheckConstraint blocks it at DB level, but `calculate_price` is also called standalone from the serializer with arbitrary context dates), the function returns bare `int 0` rather than a `Decimal`, and downstream `total_price * 100` / `quantize` behaves differently for int vs Decimal.
  2. The rate map is built with `while current <= r.end_date`, i.e. a RoomRate is treated as covering its `end_date` day too. A guest checking out on a rate's `end_date` does not occupy that night, yet the override price for `end_date` is loaded into the lookup. Booking loop uses `< check_out` (correct), but a rate whose `end_date` falls mid-stay is fine while a rate ending exactly at an interior date is double-handled. The `<=`/`<` asymmetry between the rate-expansion loop and the nights loop is an off-by-one waiting to surface when rate ranges and stays share boundaries.
- Impact: Wrong nightly price applied on boundary dates; possible int/Decimal arithmetic divergence in paise conversion. Money correctness depends on date boundaries lining up by luck.

## BSF-04 — Dev confirm path has no lock and no overlap re-check (double-confirm)
- Severity: High
- Location: `rooms/views.py:464-510` (`ProcessPaymentView`)
- Offending code:
  ```python
  booking = Booking.objects.select_related("room").get(id=booking_id, user=request.user)
  ...
  if booking.status != "pending": ...
  if booking.expire_if_needed(): ...
  booking.status = "confirmed"
  booking.save(update_fields=["status", "hold_expires_at"])
  ```
- Data flow: Reads booking → checks status literal `"pending"` → checks expiry → flips to `confirmed`. No `transaction.atomic` / `select_for_update`, and no re-check that the room isn't already confirmed for an overlapping range.
- Why it's a bug: Between hold creation and this confirm, another guest's hold could have been confirmed for overlapping dates (the hold-time overlap check excludes the caller's own pending holds and OTA, but nothing re-validates at confirm). Two concurrent confirms of the same booking row also race the read-modify-write (check-then-act on `status`). This path is `DEBUG`-gated, but it's still the documented dev confirm flow and shares the same no-lock pattern as the real verify path.
- Impact: Possible double-confirmed overlapping bookings (double-booking the room) and lost-update on the status field under concurrency.

## BSF-05 — Search/availability is check-then-act with no locking on the read path
- Severity: High
- Location: `rooms/views.py:56-87` (`get_unavailable_room_ids`), `155-164` (search filter)
- Offending code:
  ```python
  unavailable_ids = get_unavailable_room_ids(check_in, check_out)
  rooms = Room.objects.filter(...).exclude(id__in=unavailable_ids)
  ```
- Data flow: Search computes blocked room IDs from current bookings/holds/OTA, then excludes them. The hold endpoint later re-checks under a lock — good — but the search result a user acts on is a snapshot with no consistency guarantee, and `get_unavailable_room_ids` is the shared helper that the hold path does **not** reuse inside its transaction (the hold path re-implements the overlap query separately at `views.py:341-355`).
- Why it's a bug: Two divergent copies of the overlap predicate exist (helper vs in-transaction). They must stay in lockstep or search and hold disagree about availability. The helper at line 78 filters `Q(status="pending", hold_expires_at__gt=now)` while the booking model's `is_hold_expired` uses `>=` (`models.py:398`) — boundary disagreement (see BSF-07). Search is inherently racy (acceptable) but the duplicated predicate is a latent correctness drift.
- Impact: A room can show "available" in search and then 409 at hold (annoying but safe), or the two predicates drift over time and a stale hold is treated as live by one path and dead by the other.

## BSF-06 — `compute_tax` swallows every exception to `0.00`
- Severity: Medium
- Location: `rooms/models.py:477-491`
- Offending code:
  ```python
  try:
      ...
      self.tax_amount = (self.total_price * rate / Decimal('100')).quantize(Decimal('0.01'))
  except Exception:
      self.tax_amount = Decimal('0.00')
  self.save(update_fields=["tax_amount"])
  ```
- Data flow: Called at confirm time. Any failure — missing `tax_config`, `gst_rate_for` raising, Decimal error, missing property — is caught by a bare `except Exception` and the tax is silently set to zero, then saved.
- Why it's a bug: A configuration error (property has no `PropertyTaxConfig`) is indistinguishable from "this booking genuinely has zero tax." The error is neither logged nor surfaced; data is left in a plausible-but-wrong state.
- Impact: Silent tax-revenue loss; impossible to detect misconfiguration from the data. Compounds BSF-02.

## BSF-07 — Expiry boundary disagreement: task `<` vs property `>=`
- Severity: Medium
- Location: `rooms/tasks.py:14-17` vs `rooms/models.py:398` vs `rooms/views.py:78`
- Offending code:
  ```python
  # tasks.py — expire when strictly past
  hold_expires_at__lt=now
  # models.py is_hold_expired — expired when now >= expiry
  return timezone.now() >= self.hold_expires_at
  # views.py availability — live when strictly future
  Q(status="pending", hold_expires_at__gt=now)
  ```
- Data flow: Three independent definitions of "is this hold still alive" run on three code paths (background task, request-time expiry, availability query).
- Why it's a bug: At the exact instant `now == hold_expires_at`: `is_hold_expired` says expired (`>=`), the availability query says blocked/live (`> now` is false → excluded → treated as expired/free — consistent), but the bulk task says NOT expired (`< now` is false → skipped). The bulk task leaves a hold at exactly-equal time un-expired by one tick. Minor, but it's three sources of truth for one concept.
- Impact: A single hold can be considered expired by the request path while the background sweeper leaves its status `pending` for one extra cycle. No data corruption, but the inconsistency means status can lag reality.

## BSF-08 — Price frozen at hold time, never re-validated at confirm
- Severity: Medium
- Location: `rooms/views.py:307-308` (hold) and payments verify (`payments/views.py:234-240`)
- Data flow: `total_price` is computed once at hold (`calculate_price`) and stored. Payment verify confirms using the stored `total_price` / the Razorpay order amount created at hold time. If a RoomRate is edited between hold and confirm, the confirmed booking keeps the stale price.
- Why it's a bug: The price the guest pays is whatever was captured at hold; there's no re-check that it still matches `calculate_price` at confirm. For a 10-minute window this is mostly fine, but combined with the reclaim path (`views.py:332-336`) which **does** recompute `total_price` on a reclaimed hold while the Razorpay order may be reused (`views.py:410-416` reuses the order only if `amount` matches) — a recomputed price that differs from the existing order amount falls through to creating a new order, which is correct, but the booking row's `total_price` and any already-created order can momentarily disagree.
- Impact: Edge-case price/charge mismatch when rates change mid-hold or on reclaim.

## BSF-09 — No min/max price sanity check in search
- Severity: Medium
- Location: `rooms/serializers.py:129-138`, applied at `views.py:179-182`
- Offending code:
  ```python
  if min_price is not None: rooms = rooms.filter(price_per_night__gte=min_price)
  if max_price is not None: rooms = rooms.filter(price_per_night__lte=max_price)
  ```
- Data flow: `min_price`/`max_price` are validated only as Decimals; the view applies them as independent filters.
- Why it's a bug: An inverted range (`min_price > max_price`) or negative price passes validation and silently yields zero rooms with the generic "No rooms available" message, masking a client bug as an empty result.
- Impact: Confusing empty results; unvalidated numeric input reaches the ORM filter. Low blast radius but a real validation gap.

## BSF-10 — `pending`→`HELD` representation split from every status comparison
- Severity: Low
- Location: `rooms/serializers.py:244-262`
- Offending code:
  ```python
  if data.get("status") == "pending":
      data["status"] = "HELD"
  ```
- Data flow: The serializer relabels the output status, but every view guard (`views.py:484`, `556`, `685`, `737`), model method (`is_hold_expired`, `release_hold`, `expire_if_needed`), and query filter compares the raw `"pending"`/`"confirmed"` literals.
- Why it's a bug: The wire contract (`HELD`) differs from the persisted/queried value (`pending`). Any frontend or future endpoint that reads back `status` from a serialized payload and POSTs it (or compares it) will mismatch the DB literal. The mapping is one-way and only covers `pending`, not the documented HELD→CONFIRMED→COMPLETED vocabulary.
- Impact: Contract confusion; brittle if status is ever round-tripped client→server.

## BSF-11 — `MyBookingsView` expires holds row-by-row instead of via the bulk task
- Severity: Low
- Location: `rooms/views.py:737-738`
- Offending code:
  ```python
  for booking in Booking.objects.filter(user=request.user, status='pending'):
      booking.expire_if_needed()
  ```
- Data flow: Every dashboard load iterates the user's pending holds and issues a `save()` per expired row.
- Why it's a bug: N+1 writes on a hot read endpoint, and it races the bulk `release_expired_holds` task (both can flip the same row). Business logic (expiry) is correctly in the model, but invoking it in a per-row loop in the view duplicates what the background task already does.
- Impact: Extra queries per dashboard load; redundant with the worker; minor race on concurrent expiry.

## BSF-12 — Calendar includes clock-expired holds as live "HELD" events
- Severity: Low
- Location: `rooms/views.py:806-839`
- Offending code:
  ```python
  bookings = Booking.objects.filter(..., status__in=['confirmed', 'pending'])
  ...
  if b.status == 'pending' and getattr(b, 'is_hold_expired', False):
      continue
  ```
- Data flow: The query pulls all `pending` rows regardless of `hold_expires_at`, then relies on the Python-side `is_hold_expired` guard to skip expired ones. Rows with `hold_expires_at IS NULL` (e.g. released/confirmed transitions) return `False` from `is_hold_expired` and are kept.
- Why it's a bug: The filtering is done in Python after fetching, not in the DB, and the `getattr(..., False)` fallback would mask any attribute issue. A pending hold that has passed its expiry but not yet been swept by the task is correctly skipped — but only because of the Python guard, which is fragile compared to a DB-level `hold_expires_at__gt=now` filter consistent with `get_unavailable_room_ids`.
- Impact: Calendar correctness depends on a Python-side guard rather than the same DB predicate used elsewhere; drift risk with BSF-05/BSF-07.
