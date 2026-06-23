# Admin Panels — Data-Flow Bug Audit

**Scope:** Super Admin (`superadmin/`) and Employee Admin (`employeeadmin/`) panels — room CRUD, availability calendar, bookings, financial/tax config, employee management, audit log.
**Mode:** Read-only. Every finding cites file:line.
**Date:** 2026-06-17

---

## Summary Table

| ID | Severity | Title | Location |
|----|----------|-------|----------|
| ADM-01 | Critical | Employee management has no role/target guard — privilege escalation & cross-role takeover | `superadmin/views.py:197`, `:258` |
| ADM-02 | Critical | `employee_create`/`employee_update` mass-assigns role & blindly trusts any `user_id` | `superadmin/views.py:152`, `:197` |
| ADM-03 | High | Employee can block / rate a room with active bookings (no booking check on availability writes) | `employeeadmin/views.py:139`, `:167` |
| ADM-04 | High | Tax config edits never recompute existing/held bookings — stale tax | `rooms/models.py:477`, `superadmin/views.py:356` |
| ADM-05 | High | Seasonal rate stored as `float` then into `DecimalField` — money precision loss | `employeeadmin/views.py:182`, `:188` |
| ADM-06 | Medium | Availability blocks have no overlap validation; date range is a string compare | `employeeadmin/views.py:148`, `:178` |
| ADM-07 | Medium | Several mutating actions write silently — not audit-logged | `employeeadmin/views.py` (all), `superadmin/views.py:783` |
| ADM-08 | Medium | `loyalty_adjust` / `booking_*` accept any `user_id`/`booking_id`, no guest-role scoping | `superadmin/views.py:623`, `:564` |
| ADM-09 | Low | `permissions.py` role names (`employee_admin`/`super_admin`) mismatch usage; DRF gates unused/inconsistent | `accounts/permissions.py:12`, `:24` |
| ADM-10 | Low | Tax config `compute_tax` swallows all exceptions → silent ₹0.00 tax | `rooms/models.py:488` |

---

## ADM-01 — Employee management has no role/target guard (privilege escalation)

**Severity:** Critical
**Location:** `superadmin/views.py:197` (`employee_update`), `:258` (`employee_delete`), `:228` (`reset_password`)

**Data flow:** `employee_update(request, user_id)` →
```python
employee = get_object_or_404(User, pk=user_id)   # line 198
...
if action == 'reset_password':
    temp = secrets.token_urlsafe(12)
    employee.set_password(temp)                   # line 230
    employee.save()
```
The lookup is `get_object_or_404(User, pk=user_id)` against the **entire** `User` table — there is no filter on `userprofile__role='employee'`. The same is true for `employee_delete` (line 260) and `loyalty_adjust` (line 624).

**Why it's a bug:** The view is named "employee" management and the UI only lists employees, but the endpoint accepts any user UUID. A super admin (or anything that can reach this view) can `reset_password`, `lock`, `revoke`, or `update_fin` against **another super admin** or any guest. There is no `role == 'employee'` assertion anywhere between the URL parameter and the destructive write. Combined with ADM-02 this is the load-bearing access-control gap.

**Impact:** Account takeover of peer super admins via password reset; locking out other admins; arbitrary guest manipulation through an employee-scoped endpoint. The only self-protection is `employee == request.user` (line 202/262), which does not protect *other* privileged accounts.

---

## ADM-02 — Role mass-assignment & unscoped target in employee create/update

**Severity:** Critical
**Location:** `superadmin/views.py:152` (`employee_create`), `:197` (`employee_update`)

**Data flow:** `employee_create` reads `fin_level` and `property_ids` straight from POST and sets:
```python
profile.role = 'employee'          # line 178
profile.fin_level = fin_level      # line 179 — POST value, no allowlist
...
profile.assigned_properties.set(Property.objects.filter(id__in=property_ids))  # line 184
```
`employee_update` action `update_properties` (line 244) and `update_fin` (line 237) likewise set arbitrary property assignments / financial level from the JSON body with no validation that the values are legal, and `update_fin` accepts any string into `fin_level` (default `'C'`) without checking it against `FIN_LEVEL_CHOICES`.

**Why it's a bug:** `fin_level` controls financial access (A/B/C); it is written verbatim from request data. There is no allowlist check (`fin in {'A','B','C'}`), so an out-of-range value can be persisted (e.g. `fin_level='A'` granted unconditionally, or a junk value that `_fin_level()` later defaults around). Property assignment is similarly attacker-controlled. The target is any `User` (see ADM-01), so these writes are not even constrained to employees.

**Impact:** Privilege/scope escalation — granting full financial access or assigning properties without constraint, on arbitrary accounts. Mass-assignment of `fin_level` is the concrete escalation vector.

---

## ADM-03 — Availability writes ignore active bookings

**Severity:** High
**Location:** `employeeadmin/views.py:139` (`ota_block_create`), `:167` (`seasonal_rate_create`)

**Data flow:**
```python
if not start or not end or start > end:
    return JsonResponse({'error': 'Invalid date range.'}, status=400)
block = OTABlock.objects.create(room=room, start_date=start, end_date=end, reason=reason)  # line 151
```
The only validation is presence + `start > end`. There is **no check** that the date range overlaps an existing `confirmed`/`pending` `Booking` for that room.

**Why it's a bug:** An employee can block a room (or set a seasonal rate) over dates that already have a paid, confirmed guest booking. The block/rate is written with no awareness of `Booking` rows. Availability and bookings are mutated through independent paths with no consistency check between them.

**Impact:** A confirmed guest's room can be administratively blocked out from under them; seasonal rate changes silently disagree with the price the guest already paid (`Booking.total_price` was frozen at booking time — `calculate_price` in `rooms/models.py:216` reads `RoomRate` only at quote time). Operational double-booking / dispute risk.

---

## ADM-04 — Tax config edits do not recompute existing bookings (stale tax)

**Severity:** High
**Location:** `superadmin/views.py:356` (`tax_config`), `rooms/models.py:477` (`compute_tax`)

**Data flow:** `tax_config` writes `threshold` / `low_rate_pct` / `high_rate_pct` onto `PropertyTaxConfig` (lines 362-366). `Booking.compute_tax()` reads `cfg.gst_rate_for(...)` and freezes `tax_amount` — but it is only ever called at confirmation time (per its docstring at `rooms/models.py:351`). There is no recomputation hook when the config changes, and `pending` holds that confirm *after* a config edit will use the new rate while already-confirmed bookings keep the old one.

**Why it's a bug:** The tax rate applied to a booking depends on *when* the admin happened to edit the config relative to confirmation, not on a defined effective-date policy. A `pending` hold created under rate 12% can be confirmed at 18% (or vice versa) with no record of which rate the guest was quoted. There is no `effective_from`/versioning on `PropertyTaxConfig`.

**Impact:** Financial inconsistency — guests can be charged a different GST than displayed at hold time; no audit of which rate applied to which booking. The audit log records "TAX_CONFIG_UPDATED" but not the before/after values (line 367 logs only `property=`).

---

## ADM-05 — Seasonal rate uses float for money

**Severity:** High
**Location:** `employeeadmin/views.py:182`, `:188`

**Data flow:**
```python
price = float(price)              # line 182
...
rate = RoomRate.objects.create(room=room, start_date=start, end_date=end, price=price)  # line 188
```
`RoomRate.price` is a `DecimalField(max_digits=10, decimal_places=2)` (`rooms/models.py:532`). The view parses the incoming price with `float()`, not `Decimal`. Contrast the superadmin/employee room CRUD which correctly uses `Decimal(str(val))` (`superadmin/views.py:490`, `employeeadmin/views.py:267`).

**Why it's a bug:** Float → Decimal conversion introduces binary-float representation error before quantizing to 2 places. This rate later feeds `Room.calculate_price` (`rooms/models.py:240`), which sums `daily_price` values directly into a money total — propagating the imprecision into what a guest is charged.

**Impact:** Off-by-a-paisa pricing on seasonal-rate nights; inconsistent with the Decimal discipline used everywhere else. CLAUDE.md explicitly flags "money as float vs Decimal."

---

## ADM-06 — No overlap validation on availability ranges; string date comparison

**Severity:** Medium
**Location:** `employeeadmin/views.py:148` (`ota_block_create`), `:178` (`seasonal_rate_create`)

**Data flow:** Validation is `start > end` where `start`/`end` are raw POST strings (never parsed to `date`). The model has a DB `CheckConstraint(end_date >= start_date)` (`rooms/models.py:511`, `:543`) but allows `end == start` while the view rejects only `start > end` — and the view never checks for overlap against *other* blocks/rates on the same room.

**Why it's a bug:** Two flaws: (1) the string comparison works for well-formed ISO dates but is not a real date validation — a malformed value passes the `>` test and is handed to the ORM as a string. (2) Overlapping `OTABlock` rows or overlapping `RoomRate` rows can be created freely, so the "applicable rate for a date" lookup in `calculate_price` (`rooms/models.py:229-234`) becomes order-dependent (last writer in the dict wins).

**Impact:** Ambiguous/duplicate availability data; nondeterministic price overrides when ranges overlap. Calendar can show conflicting blocks.

---

## ADM-07 — Mutating actions that are not audit-logged

**Severity:** Medium
**Location:** Entire `employeeadmin/views.py`; `superadmin/views.py:783` (`room_image_set_primary`), `:374-421` loyalty tier/campaign branches

**Data flow:** `AuditLog` is written only via `superadmin._log()`. The **employee** portal has no `_log()` equivalent at all — `room_status_update` (line 101), `room_edit` (line 250), `room_create` (line 217), `ota_block_create/delete` (line 139/157), `seasonal_rate_create` (line 167), `booking_complete` (line 194), and all employee image operations write to the DB with **zero** audit trail. On the superadmin side, `room_image_set_primary` (line 783) and the loyalty `save_tier`/`delete_tier`/`save_campaign`/`delete_campaign` branches (lines 395-421) also mutate without `_log()`.

**Why it's a bug:** The domain spec calls for an audit log of admin actions, but the actor who performs the most frequent operational writes (the employee) leaves no trace. Booking status changes, room price edits, and calendar blocks by employees are invisible.

**Impact:** No accountability for employee actions; cannot reconstruct who blocked a room, changed a price, or completed a booking. Undermines the audit-log feature entirely for the employee role.

---

## ADM-08 — Booking/loyalty endpoints accept any id, no guest-role scoping

**Severity:** Medium
**Location:** `superadmin/views.py:564` (`booking_cancel`), `:578` (`booking_complete`), `:623` (`loyalty_adjust`)

**Data flow:** `loyalty_adjust(request, user_id)` does `get_object_or_404(User, pk=user_id)` then `target.userprofile.loyalty_points = max(0, ...)` (line 633) — no check that `target` is a guest. An employee/admin account (which has a `UserProfile` with `loyalty_points` defaulting to 0) can be "credited" points. Booking cancel/complete look up `Booking` by raw pk with no property scoping (acceptable for super admin, but worth noting the symmetry gap vs the employee portal which *does* scope via `room__in=rooms`).

**Why it's a bug:** Loyalty points are a guest-only concept; the endpoint mutates them on any user. Check-then-act on booking status (`if booking.status not in (...)` at line 566, then `save`) is not wrapped in a transaction or `select_for_update`, so two concurrent admin actions can race on the same booking.

**Impact:** Loyalty points assignable to non-guest accounts; minor TOCTOU on booking status transitions (low likelihood given single-admin usage).

---

## ADM-09 — DRF permission classes mismatch the role model and are inconsistent

**Severity:** Low
**Location:** `accounts/permissions.py:12`, `:24`

**Data flow:** `IsEmployee` checks `userprofile.role == 'employee_admin'` (line 12) and `IsSuperAdmin` checks `== 'super_admin'` (line 24). But the actual gating used by the views is the function decorators (`require_super_admin`, `require_employee`) in each app, which rely on `role_routing.get_user_role` and `EMPLOYEE_ADMIN_ROLES = {'employee', 'employee_admin'}` (`role_routing.py:15`).

**Why it's a bug:** `IsEmployee` only matches `employee_admin` and would **reject** a plain `employee` (the role `employee_create` actually assigns at `superadmin/views.py:178`). These DRF permission classes therefore encode a different, stricter rule than the live decorators. If they are ever wired to a view, plain employees lose access; if they are dead code, they are a misleading source of truth. Either way the project has two divergent definitions of "who is an employee."

**Impact:** Latent authorization inconsistency; confusion about the canonical role gate. Confirm whether `permissions.py` is referenced anywhere before relying on it.

---

## ADM-10 — `compute_tax` swallows all exceptions to ₹0.00

**Severity:** Low
**Location:** `rooms/models.py:488`

**Data flow:**
```python
try:
    ...
    rate = cfg.gst_rate_for(nightly_rate)
    self.tax_amount = (self.total_price * rate / Decimal('100')).quantize(Decimal('0.01'))
except Exception:
    self.tax_amount = Decimal('0.00')   # line 489
self.save(update_fields=["tax_amount"])
```
Any error — missing `PropertyTaxConfig` (the `RelatedObjectDoesNotExist` from `prop.tax_config`), a `None` property, arithmetic issues — is caught and silently sets tax to zero.

**Why it's a bug:** A property with no tax config produces a confirmed booking with `tax_amount = 0.00` and no signal that tax was skipped. The failure is indistinguishable from a legitimately tax-free booking.

**Impact:** Silent under-collection of GST when a tax config is missing or misconfigured; no error surfaced to the admin who forgot to set it up.

---

## Notes on what is correctly scoped (no finding)

- The **employee** portal consistently scopes room/booking/availability mutations to assigned properties: `_assigned_rooms()` returns `Room.objects.none()` when unassigned (`employeeadmin/views.py:31`), and every write re-checks membership (`room_edit:255`, `room_status_update:102`, `ota_block_delete:159`, image ops `:318/:342/:354`, `booking_complete:197`). This is the right pattern — no cross-tenant IDOR was found in the employee portal.
- `seasonal_rate_create` correctly gates on `fin == 'C'` (line 169).
- Employee `room_create` correctly verifies the target property is assigned (line 222).
</content>
</invoke>
