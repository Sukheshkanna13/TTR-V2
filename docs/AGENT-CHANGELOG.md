# Agent Change Log

A running record of changes made by AI coding sessions, newest first. Each entry
lists the problem, the root cause, and what changed, so future sessions have
context without re-deriving it.

---

## 2026-06-15 — Booking hold early-release + My Stays cleanup

Branch: `fix/superadmin-employee-management`

### Bug 1 — Room hold never released on abandoned payment

**Symptom:** When a guest left checkout (closed the Razorpay modal, payment
failed, refreshed, or hit Back), the room stayed locked for the full 10-minute
hold — blocking other guests and even the same guest from re-booking.

**Root cause:** A `pending` booking blocks its room in every availability query
while `hold_expires_at > now`. The only release paths were successful payment,
the qcluster sweep, a lazy `expire_if_needed()` on read, and cancelling a
confirmed booking. **There was no early-release path for an abandoned/failed
payment.** The checkout JS handlers (`modal.ondismiss`, `payment.failed`,
back-link) only reset the UI, and `VerifyPaymentView`'s signature-failure branch
marked only the `Payment` row failed, leaving the booking `pending`. The sweep
also ran every 10 min, so other guests could wait up to ~20 min.

**Fix (scalable, OTA-ready — release immediately, keep sweep as safety net):**

- `rooms/models.py` — `Booking.release_hold(reason)`: single source of truth.
  `pending` → `expired` (abandon/timeout) or `failed` (payment_failed); nulls
  `hold_expires_at`; idempotent (safe for repeat / beacon calls).
- `rooms/views.py` — `ReleaseHoldView` (`POST /bookings/<id>/release/`),
  ownership-scoped + idempotent. Uses `CsrfExemptSessionAuthentication` so it can
  be called via `navigator.sendBeacon` on unload (low risk: only releases the
  caller's own pending hold).
- `rooms/views.py` — `HoldRoomView` now **reclaims** the guest's own existing
  pending hold for the same room+dates instead of returning 409, and excludes the
  guest's own pending holds from the conflict check. Reuses the existing Razorpay
  order on reclaim.
- `payments/views.py` — `VerifyPaymentView` signature-fail branch and the webhook
  `payment.failed` event now call `booking.release_hold('payment_failed')`, so the
  room frees even if the client never pings.
- `templates/payments/checkout.html` — wires `ondismiss`, `payment.failed`, and
  the back-link to release; `pagehide` fires `navigator.sendBeacon` to catch
  refresh / Back / tab-close. **Deliberately does NOT release on
  `visibilitychange` or while a payment attempt is in flight** — during real
  UPI/OTP flows the guest backgrounds the tab to approve in their bank app, and
  releasing then would break a legitimate payment. The 1-min sweep covers the rare
  mid-payment abandonment.
- `rooms/apps.py` — `release_expired_holds` sweep tightened from every 10 min to
  every 1 min (uses `update_or_create` so existing schedules migrate), keeping
  inventory accurate for OTA sync.

Tests: `rooms/tests.py` — `ReleaseHoldModelTest`, `ReleaseHoldEndpointTest`,
`SameUserReclaimTest`.

### Bug 2 — My Stays (folio) showed abandoned attempts

**Symptom:** The folio page listed every booking status (pending/expired/failed)
and counters built from them.

**Fix:** `accounts/views.py` `folio_page` now passes only confirmed + completed
stays, total nights stayed, total spent, and real loyalty (`loyalty_points` /
`loyalty_tier`) instead of a nights proxy. `templates/pages/folio.html` rebuilt:
slim stats (Confirmed Stays / Total Nights Stayed / Wayfarer Points), stays-only
history, Wayfarer Rewards driven by real loyalty data, and an Account card with
Edit profile + **Change password** links.

Tests: `accounts/tests.py` — `FolioPageTests`.

### Cleanup
Removed stray macOS Finder duplicate template folders (`templates/* 2`).

Full suite: **70/70 passing.**

---

## 2026-06-15 — Super Admin employee management rebuild

Branch: `fix/superadmin-employee-management`. See
`docs/superpowers/specs/2026-06-15-superadmin-employee-management-design.md`.

**Root cause:** employee/loyalty routes used `<int:user_id>` but `User.id` is a
UUID, so every edit/lock/reset/property action 404'd.

**Changes:** routes → `<uuid:user_id>`; `UserProfile` gained `created_by`,
`revoked_at`, `revoked_by` + `revoke()`, `reinstate()`, `can_hard_delete`;
superadmin views record `created_by`, add revoke/reinstate + `employee_delete`
(hard delete only for never-logged-in accounts) with a self-protection guard;
`AuditLog` gained `EMPLOYEE_REVOKED`/`EMPLOYEE_DELETED`; `employees.html` gained
tracking columns (created / last login / created by / PW status), Active/Locked/
Revoked states, and a copy-once credential modal (replacing the plaintext alert +
3s auto-hide). Removed the dead shadow template
`superadmin/templates/superadmin/employees.html`. 11 new tests.
