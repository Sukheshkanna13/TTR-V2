# Admin Panels Audit — Super Admin + Employee Admin (2026-10-18)

**Branch:** `feat/channex-foundation` · **Scope:** `superadmin/`, `employeeadmin/`, their templates, and the services/tasks they call.
**Method:** full read of both `views.py` files + decorators/urls/templates, existing tests (38/38 pass), and a live probe script that hit every risky endpoint on a throwaway test DB. Items marked **[probed]** were reproduced, not just read.

**Headline:** the existing tests pass but don't exercise bad input, fin-level limits, or the dashboard JS. **4 critical, 7 high, 8 medium** issues found. Fix the criticals before the next push to prod.

---

## 🔴 Critical

### C1. Stored XSS: a guest can run JS in the Super Admin's session [probed]
- `templates/superadmin/dashboard.html:224` builds pending-hold rows with `tr.innerHTML = \`...${h.guest}...${h.room}...\``. The data comes from `/super-admin/dashboard/live/` (`superadmin/views.py:110-127`).
- `h.guest` is the guest's `full_name`, which the guest sets themselves at signup. A guest named `<img src=x onerror=...>` who starts a booking hold gets code running in the super admin's browser on the next 15s poll. That code can create employees, change prices, and read financials.
- Same pattern: `templates/superadmin/rooms.html:334` puts `${opt}` (room **amenities**) into `innerHTML`. Employees can edit amenities, so an **employee can escalate to super admin**.
- **Fix:** build cells with `textContent`, or add an `esc()` helper and wrap every interpolated value. Grep all `innerHTML = \`` sites in `templates/superadmin` and `templates/employeeadmin`.

### C2. "Mark completed" before check-out frees the room, so it can be double-booked [probed]
- `booking_complete` in both panels (`superadmin/views.py:836`, `employeeadmin/views.py:300`) accepts any confirmed booking, including stays that haven't started or are in progress.
- The availability checks (`rooms/models.py:115`, `rooms/views.py:441`, `core/ota/availability.py:59`) only treat `confirmed` and live `pending` as occupied. A `completed` booking stops blocking its nights, so the room reappears on the website and for walk-ins.
- **Fix:** allow completion only when `check_out <= today` (or `check_in <= today` for an early checkout, and in that case shorten `check_out` and push availability). Add `record_ari_change` for the freed nights.

### C3. Revenue analytics drop every finished stay [read]
- The dashboard `month_revenue` (`superadmin/views.py:59`) and all of Analytics (`:339`, `:350`) filter `status='confirmed'` only.
- `auto_complete_bookings` (`rooms/tasks.py:73`) flips every past stay to `completed`. So last month's revenue, booking counts, occupancy and cancellation rate all **shrink toward zero over time**. Super Admin financials are wrong.
- **Fix:** use `status__in=('confirmed', 'completed')` for revenue, counts and occupancy.

### C4. Fin-level C employees can change prices [probed]
- A fin=C employee (no financial access) can:
  - set a room's base price to ₹1 via `room_edit` `update_details` (`employeeadmin/views.py:364`). That change is also pushed to Channex/OTAs.
  - create walk-ins with `price_override=1` (`employeeadmin/views.py:131`).
  - create rooms with any price.
- Only seasonal rates are gated (`:272`). The templates (`templates/employeeadmin/rooms.html:91,108,149`) show and edit prices with no `fin` check.
- **Fix:** gate `price_per_night` edits, `price_override` and room-create price on `fin in ('A','B')`. Hide the fields in the templates for C.

---

## 🟠 High

### H1. Employee Admin writes zero audit records [probed: 0 rows]
- No employee view calls `AuditLog`: walk-ins, price edits, OTA blocks, rate changes, completions, room create/toggle, and image deletes are all untraceable. CLAUDE.md promises an audit trail.
- Super Admin gaps:
  - walk-in creation is logged as `BOOKING_COMPLETED` (`superadmin/views.py:803`).
  - banner create is logged as `PROPERTY_UPDATED` (`:1521`).
  - `banner_toggle`, `banner_delete`, `room_image_set_primary`, `event_image_set_primary`, and loyalty tier/campaign/config saves log nothing or no values.
  - 13 action codes used in code (`CAUSE_*`, `EVENT_*`, `ACTIVITY_*`, `REDEMPTION_RULE_*`) are missing from `AuditLog.ACTION_CHOICES` (`superadmin/models.py:8`). They can't be filtered in the audit-log UI and show as raw codes.
- **Fix:** move `_log` into `core` or `superadmin/audit.py`, call it from every mutating employee view, and add the missing choices (no migration is needed; choices aren't a DB constraint). Log old→new values for price, tax and loyalty changes.

### H2. Unvalidated input causes 500 errors (17 probed endpoints)
Every one of these returns HTTP 500 instead of a 400 [probed]:

| Endpoint | Input |
|---|---|
| SA `/bookings/` | `?property=abc`, `?from=notadate` |
| SA + EMP `/rooms/` | `?property=abc` |
| SA + EMP `rooms/create` | `price_per_night=abc` (`Decimal` raises `InvalidOperation`, which `except (ValueError, TypeError)` doesn't catch) |
| SA `rooms/create` | `room_type` not in choices |
| SA `room_update`, EMP `room_edit` | malformed JSON; `rating=abc`; `capacity=abc` |
| SA `tax-config` | `threshold=abc` |
| SA `loyalty-config` | `save_config`/`save_tier` non-numeric, `save_campaign` missing dates |
| SA `banners/create` | `sort_order=abc` |
| EMP `availability/block/create` | non-date strings |
| EMP walk-in | `guests=-3` |

Also by inspection: `employee_update`, `property_update`, `event_update`, `cause_update`, `activity_update` (`json.loads`), and `event_image_upload` (`int(sort_order)`).

- **Fix:** add a small `parse_json(request)` helper and `to_decimal`/`to_int` helpers that return 400. Validate UUID/date query params before filtering (or switch to Django forms). Add these cases to `superadmin/tests_smoke.py`.

### H3. Walk-in bookings accept bad data [probed]
- `payment_method='bitcoin'` was accepted and recorded as **captured** (`rooms/services.py:120`).
- `guests=50` was accepted for a capacity-2 room.
- A negative price override is silently replaced with the standard price.
- The guest lookup by email/phone (`rooms/services.py:55-61`) can attach a walk-in to a **staff account** if the numbers match.
- **Fix:** validate `payment_method in dict(Payment.METHOD_CHOICES)`, `1 <= guests <= room.capacity`, and `override > 0`. Restrict the guest lookup to `userprofile__role='guest'`.

### H4. `auto_complete_bookings` writes an invalid room status [probed]
- `rooms/tasks.py:84` sets `operational_status = "needs_cleaning"`, but the valid choice is `"cleaning"`. Status boards show a grey raw badge and the dropdowns have nothing selected.
- **Fix:** use `Room.STATUS_CLEANING` and add a data migration to repair existing rows.

### H5. Super Admin cancel is incomplete
`booking_cancel` (`superadmin/views.py:820`) has these gaps:
- no Channex availability push, so the room stays closed on OTAs
- no guest email/WhatsApp
- no refund path or flag
- the coupon is released only for `pending` bookings

The cancellation/refund plan is still unimplemented (see all-in-brief).
- **Minimum fix now:** `record_ari_change(... "availability")` on cancel, and log the refund as owed.

### H6. Room changes not pushed to Channex
- `room_create` (both panels) and `toggle_active` (both panels) never call `record_ari_change`, so new or deactivated rooms don't update OTA availability.
- `_room_update_details` in Super Admin can change `room_type` or `property` without pushing either the old or the new type.
- **Fix:** push availability for both old and new `(room_type, property)` on these actions.

### H7. Room types and prices are not validated
- `room_type` isn't checked against `ROOM_TYPE_CHOICES` (500 errors, and it would break the Channex room-type mapping).
- Negative prices are accepted (`price=-500` → 200 [probed]).
- Capacity 0 is accepted.

---

## 🟡 Medium

1. **Occupancy maths** (`superadmin/views.py:364-387`):
   - The date range is inclusive, but `days = (to - from).days` is off by one.
   - Stays that cross the range edge count all their nights, so occupancy can exceed 100%.
   - `from > to` is accepted silently.
2. **Dashboard KPIs:**
   - "Today revenue" is the sum of today's *arrivals'* `total_price`, not the money collected today.
   - `total_rooms` includes inactive rooms.
3. **Tax config** accepts negative or 500% GST and `low > high` [probed]. There are no bounds, and the audit row has no values.
4. **OTA blocks:**
   - No check against existing confirmed bookings, so you can block over a stay.
   - Dates are compared as strings.
   - `seasonal_rate_create` stores a `float` in a Decimal field.
   - Overlapping rates aren't detected.
5. **Image uploads** have no type or size validation. This was flagged on Oct 4 and is still open.
6. **The `employee_admin` role is invisible to Super Admin:**
   - The employees list filters `role='employee'` (`superadmin/views.py:143`).
   - `employee_update` and `employee_delete` refuse anything that isn't `employee` (`:276`, `:306`).
   - So an `employee_admin` user (role exists since migration `0005`) can't be listed, locked or revoked from the panel.
   - **Fix:** use `role__in=EMPLOYEE_ADMIN_ROLES`.
7. **Room status is ignored by availability** (`core/ota/availability.py:13`, documented as intentional). A room set to `out_of_order` or `maintenance` is still bookable online and on OTAs, and the "availability" pushes on status change send unchanged numbers. This is a product decision; confirm it's wanted.
8. **Dead shadowed templates:** `employeeadmin/templates/employeeadmin/*` (5 files) and `superadmin/templates/superadmin/*` (7 files) are overridden by `templates/` (`DIRS` wins). Edits there do nothing, so delete them. The same applies to the `* 2.py` duplicates (`core/ota/processor 2.py`, `payments/services 2.py`, `core/middleware 2.py`, `loyalty/urls 2.py`).

## ⚪ Low
- `_cause_toggle_active` (`superadmin/views.py:1108`) has stray `@require_super_admin @require_POST` decorators on a helper.
- `guests_list` runs an N+1 booking-count query per row. Use `annotate(Count(...))`.
- Employee `room_images` returns JSON 403 to a browser page navigation.
- `room_status_update` hard-codes the status set instead of using `Room.OPERATIONAL_STATUS_CHOICES`.

---

## Suggested fix order (one PR each)
1. **C1 XSS** (template-only, about 30 min) + **C4 fin gating** + **C2 complete-guard**: these are security and money issues.
2. **C3 revenue statuses** + **H4 `needs_cleaning`** + data migration.
3. **H2 input-hardening helpers** + extend `tests_smoke.py` with the probe cases above (they become regression tests).
4. **H1 audit logging** for Employee Admin + missing `ACTION_CHOICES`.
5. **H3 walk-in validation**, **H5/H6 Channex pushes**, **H7 room validation**.
6. Mediums.

## Re-running the probe
The probe script used for this audit lives outside the repo. Ask to have it turned into `superadmin/tests_hardening.py` so these checks run with `manage.py test`.
