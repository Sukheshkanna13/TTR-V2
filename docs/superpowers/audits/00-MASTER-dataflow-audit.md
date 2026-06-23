# TTR-V2 Internal Data-Flow Audit — Master Report

**Date:** 2026-06-17
**Method:** 5 parallel read-only auditor agents, one per data-flow domain. Documentation only — **no code was changed.**
**Scope:** First-party apps (~8,700 LOC): `accounts`, `rooms`, `payments`, `superadmin`, `employeeadmin`, `loyalty`, `core`, `hotel_booking` settings.

## Totals

| Domain | File | Total | Critical | High | Medium | Low |
|--------|------|------:|---------:|-----:|-------:|----:|
| Booking / hold / search / pricing | [01-booking-search.md](01-booking-search.md) | 12 | 2 | 3 | 4 | 3 |
| Payments (Razorpay + side effects) | [02-payments.md](02-payments.md) | 8 | 1 | 2 | 3 | 2 |
| Accounts / auth (OTP, OAuth, roles) | [03-accounts-auth.md](03-accounts-auth.md) | 13 | 3 | 4 | 4 | 2 |
| Admin panels (super + employee) | [04-admin-panels.md](04-admin-panels.md) | 10 | 2 | 3 | 3 | 2 |
| Loyalty / core tasks / settings | [05-loyalty-core-settings.md](05-loyalty-core-settings.md) | 12 | 2 | 4 | 5 | 1 |
| **TOTAL** | | **55** | **10** | **16** | **19** | **10** |

> Critical and High findings are enumerated below. Medium/Low live in the per-domain files.

---

## Cross-cutting root causes

Most of the serious findings trace to six recurring patterns. Fixing these patterns kills clusters of findings at once:

1. **No transaction boundary / no row locking.** Confirm-booking, payment-verify, loyalty-award, and admin status-toggles all do *check-then-act* and *read-modify-write* without `transaction.atomic()` + `select_for_update()` (or `F()`). → BSF-04, BSF-05, PAY-02, PAY-03, LOY-01, LOY-02.
2. **No idempotency on side effects.** Browser `verify` and Razorpay `webhook` are two paths into the same confirmation; nothing stops both running → double points, double invoice/WhatsApp. → PAY-02, LOY-01, CORE-01.
3. **Trust-boundary gaps.** Payment amount is never reconciled against the order/booking total (signature valid ≠ amount correct). OTP isn't bound to a purpose. OAuth auto-merges on email string without `email_verified`. → PAY-01, AUTH-01, AUTH-02.
4. **Object-level authorization missing.** Super-admin employee endpoints look up `User` by raw pk with no role filter; `fin_level`/property assignment are mass-assigned. → ADM-01, ADM-02.
5. **Role checks diverge across layers.** `accounts/permissions.py`, `accounts/backends.py`, `accounts/models.py`, and the live view decorators each encode roles/tiers differently. → AUTH-06, ADM-09, LOY-03, CORE-02.
6. **Money as `float` / tax not actually charged.** GST computed and stored but never added to `total_price`; seasonal rates parsed with `float()` into `DecimalField`. → BSF-02, ADM-05, BSF-03.

---

## Critical findings (10)

| ID | Title | Location |
|----|-------|----------|
| BSF-01 | `auto_complete_bookings` sets dead literal `"needs_cleaning"` (migration renamed it to `"cleaning"`); completed-stay rooms vanish from inventory permanently | rooms/tasks.py:41 |
| BSF-02 | GST stored in `tax_amount` but never added to `total_price` — Razorpay charges pre-tax; tax is a write-only orphan column | rooms/models.py:477-491 |
| PAY-01 | Paid amount never verified against booking total; valid signature confirms booking with no check that captured amount == order amount | payments/views.py:201-236, 381-396 |
| AUTH-01 | OTP keyed only by email, no purpose/subject binding — a registration/resend code satisfies forgot-password & email-change → account takeover | accounts/utils.py:66; accounts/views.py:636-651 |
| AUTH-02 | Google login auto-links to existing local account on email-string match with no `email_verified` check → OAuth account takeover | accounts/adapter.py:7-34 |
| AUTH-03 | resend/register reset OTP attempt counter to 0 with no send throttle → unlimited 3-guess windows brute-force a 6-digit OTP (plus non-constant-time `!=`) | accounts/utils.py:105; accounts/views.py:312-341 |
| ADM-01 | Employee-mgmt looks up `User` by raw pk with no `role='employee'` filter; `reset_password`/`lock`/`revoke` work on any user incl. peer super admins | superadmin/views.py:197, 258 |
| ADM-02 | `fin_level` and property assignment mass-assigned from request with no allowlist → financial-access escalation on arbitrary accounts | superadmin/views.py:152, 197 |
| LOY-01 | No idempotency on point award; verify-callback and webhook both call `award_booking_points` → race double-credits points | loyalty/services.py:12 (callers payments/views.py:264, 410) |
| SET-01 | Hardcoded MySQL password (`'vengeance'`) committed in base settings; DB block is fully literal despite "env override" comment | hotel_booking/settings/base.py:106-115 |

## High findings (16)

| ID | Title | Location |
|----|-------|----------|
| BSF-03 | `calculate_price` seeds total as `int 0` (int/Decimal mix) + rate map uses inclusive `<= end_date` while nights loop uses `< check_out` — boundary off-by-one | rooms/models.py:216-244 |
| BSF-04 | Dev `ProcessPaymentView` confirms with no `select_for_update`/atomic and no overlap re-check — double-confirm / lost update | rooms/views.py:464-510 |
| BSF-05 | Two divergent copies of the overlap predicate (search helper vs in-transaction hold query); search availability is an unlocked snapshot that can drift | rooms/views.py:56-87, 341-355 |
| PAY-02 | No idempotency / no `select_for_update`; browser verify and webhook both process same payment → double loyalty + double invoice/WhatsApp | payments/views.py:182-264, 376-410 |
| PAY-03 | Confirmation non-atomic: status flip, `generate_booking_reference()`, `compute_tax()`, Payment update, emails are separate saves with no wrapping atomic | payments/views.py:234-264, 382-410 |
| AUTH-04 | Login backend lookup doesn't normalize email — diverges from normalized lockout buckets and case-sensitive `User.email` | accounts/backends.py:29-48 |
| AUTH-05 | Email-change verify resolves OTP by client email only (compounds AUTH-01) | accounts/views.py:546-559 |
| AUTH-06 | `IsSuperAdmin` ignores `is_superuser`; `IsEmployee` rejects `super_admin`; both diverge from `get_user_role` | accounts/permissions.py:3-25 |
| AUTH-07 | CSRF globally disabled on session-auth APIs | accounts/backends.py:12-21 |
| ADM-03 | Availability block/rate writes never check for active bookings — a confirmed guest's room can be blocked | employeeadmin/views.py:139, 167 |
| ADM-04 | Tax config edits never recompute bookings; pending holds confirm at new rate, confirmed keep old — no effective-date policy | rooms/models.py:477; superadmin/views.py:356 |
| ADM-05 | Seasonal rate parsed with `float()` into a `DecimalField` — money precision loss | employeeadmin/views.py:182, 188 |
| LOY-02 | Read-modify-write on `loyalty_points` with no atomic/`select_for_update`/`F()`; concurrent award + admin adjust lose updates | loyalty/services.py:85-87; superadmin/views.py:632-634 |
| LOY-03 | Two tier systems: DB-driven `_update_tier` vs hardcoded 1500/500/0 `recalculate_tier` — same points classify differently by last writer | loyalty/services.py:104-115 vs accounts/models.py:299-307 |
| LOY-04 | Cancelled/refunded/expired bookings keep points; `REFUND_DEDUCTION` ledger reason defined but never written | loyalty/services.py:12; loyalty/models.py:84 |
| SET-02 | Insecure `SECRET_KEY` default + `DEBUG=True` default; `prod.py` never asserts `SECRET_KEY`, so a missing env var boots prod on the public key | hotel_booking/settings/base.py:21-22 |

---

## Notable Medium/Low themes (detail in domain files)

- **Expiry boundary disagreement:** three different definitions of "expired" (`<` / `>=` / `>`) across hold logic (BSF-07); per-row expiry loop races the bulk task (BSF-11).
- **No employee-portal audit logging** — employee mutations are unlogged (ADM-07).
- **`loyalty_adjust` accepts any user**, not just guests (ADM-08).
- **Role-name drift:** `IsEmployee` checks `'employee_admin'` but the assigned role is `'employee'` (ADM-09).
- **`compute_tax` swallows all exceptions to ₹0.00** (ADM-10 / BSF-06).
- **Loyalty multiplier keyed on future `check_in`, not booking time** (LOY-07).
- **Coupon redemption contract unimplemented** (LOY-08).
- **Stale/duplicate WhatsApp task on retry + dual path** (CORE-01).

## Non-findings (verified safe)

- HMAC/signature verification itself is correct (SDK for browser path, `hmac.compare_digest` for webhook). The exposure is amount reconciliation + idempotency, not the signature.
- Employee portal property-scoping (`_assigned_rooms`, re-checked on every write) is solid — **no cross-tenant IDOR** in the employee portal. The authz gaps are in the unscoped super-admin user/employee endpoints.
- No illegal direct `hotel_booking.settings.base` imports.
- Background tasks correctly use django-q `async_task` (not threading/celery).

---

## Suggested triage order (if/when fixes are authorized)

1. **SET-01 + SET-02** — rotate the committed DB password, purge from settings, fail-closed on missing prod `SECRET_KEY`. (Smallest change, highest blast radius.)
2. **PAY-01 + PAY-02 + PAY-03 + LOY-01** — one atomic, idempotent confirm path reconciling amount; collapses the payment + loyalty money-integrity cluster.
3. **AUTH-01/02/03** — bind OTP to purpose, require `email_verified` on OAuth merge, throttle OTP sends + constant-time compare.
4. **ADM-01 + ADM-02** — scope/allowlist the super-admin user-management endpoints.
5. **BSF-01 + BSF-02** — fix the dead `"cleaning"` literal and actually charge tax.
6. Reconcile the role/tier definitions into one source of truth (AUTH-06, ADM-09, LOY-03, CORE-02).

*This is an audit artifact. No fixes were applied. Each ID is fully detailed with code quotes in its domain file.*
