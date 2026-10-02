# Audit 05 — Loyalty / Core / Settings Data-Flow Audit

**Scope:** `loyalty/{models,services,views,context_processors}.py`, `core/{models,tasks,views,urls}.py`, `hotel_booking/settings/{base,dev,prod}.py`
**Date:** 2026-06-17
**Mode:** Read-only data-flow audit

## Summary

| ID | Severity | Title | Location |
|----|----------|-------|----------|
| LOY-01 | Critical | No idempotency on point award — verify + webhook double-credit | `loyalty/services.py:12` / `payments/views.py:264,410` |
| LOY-02 | High | Point earn not atomic / no `select_for_update` — concurrent award & adjust race, lost updates | `loyalty/services.py:85-87`, `superadmin/views.py:632-634` |
| LOY-03 | High | Two conflicting tier systems (DB `LoyaltyTier` vs hardcoded 1500/500/0) silently disagree | `loyalty/services.py:104-115` vs `accounts/models.py:299-307` |
| LOY-04 | High | Cancelled / refunded / expired bookings keep points — no reversal path; `REFUND_DEDUCTION` reason defined but never written | `loyalty/services.py:12`, `loyalty/models.py:84` |
| LOY-05 | Medium | `tier`/`min_pts` name mismatch — `_update_tier` writes free-text tier name into a 3-choice field; misclassifies if Super Admin renames tiers | `loyalty/services.py:110-113`, `accounts/models.py:241-253` |
| LOY-06 | Medium | Broad `except Exception` swallows award failures silently; ledger + balance can diverge mid-write | `loyalty/services.py:100-101,82-95` |
| LOY-07 | Medium | `month_count` / multiplier logic uses `check_in` not booking-creation time; future-dated re-bookings can trigger or dodge multiplier | `loyalty/services.py:57-66` |
| LOY-08 | Medium | No coupon-redemption code exists — `COUPON_REDEMPTION` ledger reason is a dead contract; balance never debited on redemption | `loyalty/models.py:83`, repo-wide |
| SET-01 | Critical | Hardcoded production DB credentials in `base.py` (`PASSWORD='vengeance'`), committed to VCS | `hotel_booking/settings/base.py:106-115` |
| SET-02 | High | Insecure `SECRET_KEY` default + `DEBUG=True` default in base; prod relies on env override only | `hotel_booking/settings/base.py:21-22` |
| CORE-01 | Medium | `send_whatsapp_message` enqueued with object data captured at call time; booking can change/expire before task runs; no retry-dedup | `payments/views.py:268,414`, `core/tasks.py:7` |
| CORE-02 | Low | `loyalty_context` reads `userprofile` every request; tier from DB can lag `profile.loyalty_tier`, showing inconsistent tier UI | `loyalty/context_processors.py:17-27` |

**Total: 12** — Critical 2, High 4, Medium 5, Low 1.

---

## LOY-01 — No idempotency on point award (double-credit)
**Severity:** Critical
**Location:** `loyalty/services.py:12` (`award_booking_points`), called from `payments/views.py:264` (verify) and `payments/views.py:410` (webhook).

**Data flow:** Razorpay confirmation arrives via *two* independent paths: the browser callback `VerifyPaymentView` (line 264) and the server-to-server `WebhookView` (line 410). Both call `award_loyalty_points(booking)` → `award_booking_points(booking.pk)`. The webhook guards booking *status* (`if booking.status == "confirmed": skip`, line 376), but the verify path sets status to confirmed and awards in the same flow with no flag. If the webhook fires before the verify callback returns (common — Razorpay webhooks are fast), the webhook sees `pending`, confirms, and awards; then the verify callback also awards. `award_booking_points` itself does **no** check for an existing `LoyaltyLedger` row for that booking:

```python
LoyaltyLedger.objects.create(
    user=user, booking=booking, delta=final_pts,
    reason='BOOKING_CONFIRMED', ...)
```

**Why it's a bug:** There is no `get_or_create` / uniqueness guard on `(booking, reason='BOOKING_CONFIRMED')`. Two awards create two ledger rows and add `final_pts` twice to `profile.loyalty_points`.

**Impact:** Guests earn double (or more) points per booking on any race or webhook+callback overlap. Inflates tier, inflates eventual coupon value. Critical accounting integrity failure.

---

## LOY-02 — Non-atomic point mutation, lost updates under concurrency
**Severity:** High
**Location:** `loyalty/services.py:85-87`; same pattern `superadmin/views.py:632-634`.

**Data flow:**
```python
profile, _ = UserProfile.objects.get_or_create(user=user)
profile.loyalty_points = (profile.loyalty_points or 0) + final_pts
profile.save(update_fields=['loyalty_points'])
```
This is read-modify-write in Python with no `transaction.atomic()`, no `select_for_update()`, and no `F()` expression. Super Admin's `loyalty_adjust` (`superadmin/views.py:633`) does the identical pattern: `profile.loyalty_points = max(0, profile.loyalty_points + amount)`.

**Why it's a bug:** Concurrent award (LOY-01's two paths) or an award racing a Super Admin adjustment read the same stale `loyalty_points`, each add their delta, and the last `save()` wins — the other delta is lost. Should be `F('loyalty_points') + delta` inside `transaction.atomic()` / `select_for_update()`.

**Impact:** Silent point loss or gain on concurrent writes; balance drifts from the `LoyaltyLedger` audit trail it is supposed to mirror.

---

## LOY-03 — Two conflicting tier systems
**Severity:** High
**Location:** `loyalty/services.py:104-115` (`_update_tier`, DB-driven `LoyaltyTier`) vs `accounts/models.py:299-307` (`recalculate_tier`, hardcoded 1500/500/0).

**Data flow:** After awarding, `award_booking_points` calls `_update_tier(profile)` which reads `LoyaltyTier` from the DB (runtime-configurable, per spec). But Super Admin's `loyalty_adjust` (`superadmin/views.py:635`) calls `profile.recalculate_tier()`, which hardcodes:
```python
if self.loyalty_points >= 1500:  self.loyalty_tier = 'gold'
elif self.loyalty_points >= 500: self.loyalty_tier = 'silver'
else: self.loyalty_tier = 'bronze'
```

**Why it's a bug:** Booking awards and admin adjustments classify the *same* points into *different* tiers using different thresholds. The CLAUDE.md spec mandates "nothing hardcoded," yet `recalculate_tier` ignores the `LoyaltyTier` table entirely. The displayed tier depends on which write happened last.

**Impact:** Tier (and thus discount %) is non-deterministic and contradicts the configurable model. Guests can be over- or under-tiered relative to the Super Admin's configured thresholds.

---

## LOY-04 — Cancelled/refunded/expired bookings keep points
**Severity:** High
**Location:** `loyalty/services.py:12`; `loyalty/models.py:84` (`REFUND_DEDUCTION` reason defined).

**Data flow:** `award_booking_points` only ever *adds*. `LoyaltyLedger.REASON_CHOICES` defines `REFUND_DEDUCTION` and `COUPON_REDEMPTION`, but a repo-wide grep shows **no code writes either reason**. When a booking is later cancelled/refunded/expired (statuses exist: `rooms/models.py:310-317`), nothing deducts the points already credited. Also `booking = models.ForeignKey(..., on_delete=models.SET_NULL)` (`loyalty/models.py:93-98`) — if a booking row is deleted, the ledger entry keeps the points with a null booking, so awards survive even hard-deletion.

**Why it's a bug:** Earn is irreversible in code; the reversal contract (`REFUND_DEDUCTION`) is declared but unimplemented. The audit context explicitly asks whether a cancelled/refunded booking can keep points — it can.

**Impact:** Guests keep loyalty points (and any tier/discount they unlock) for stays they never paid for or that were refunded. Direct monetary leakage via discounts.

---

## LOY-05 — Tier name vs choice-field mismatch
**Severity:** Medium
**Location:** `loyalty/services.py:110-113`; field `accounts/models.py:241-253`.

**Data flow:** `_update_tier` does `new_tier = tiers.first().name.lower()` and writes it to `profile.loyalty_tier`. But `loyalty_tier` is a `CharField(max_length=20, choices=TIER_CHOICES)` whose choices are only `bronze/silver/gold`. `LoyaltyTier.name` is a free-text `CharField(max_length=50, unique=True)` the Super Admin controls.

**Why it's a bug:** If an admin names a tier "Platinum" or "Silver Plus", `_update_tier` writes a value outside `TIER_CHOICES` (no DB constraint enforces choices, so it persists silently) and may exceed semantic expectations elsewhere. The context processor (`context_processors.py:17`) then falls back to `'bronze'` display logic on mismatch. Tier mapping silently misclassifies.

**Impact:** Renaming tiers (a supported Super Admin action) breaks the guest's stored tier string and any template/branching keyed on `bronze/silver/gold`.

---

## LOY-06 — Silent failure swallows divergence
**Severity:** Medium
**Location:** `loyalty/services.py:100-101`; write block `82-95`.

**Data flow:** The entire body of `award_booking_points` is wrapped in `try/except Exception: logger.exception(...)`. The balance update (`save` at line 87) and the ledger insert (line 89) are **not** in one `transaction.atomic()`. If `profile.save()` succeeds but `LoyaltyLedger.objects.create()` raises (e.g. DB hiccup), the balance is bumped with no audit row, and the exception is swallowed — caller sees success.

**Why it's a bug:** Partial write + swallowed exception means balance and ledger silently diverge with no signal. Caller (`payments/utils.award_loyalty_points`) also wraps in try/except, so payment confirmation reports success regardless.

**Impact:** Untraceable balance drift; no alerting. Makes LOY-01/LOY-02 corruption invisible.

---

## LOY-07 — Multiplier keyed on check-in date, not booking time
**Severity:** Medium
**Location:** `loyalty/services.py:57-66`.

**Data flow:** `today = booking.check_in` (a future date). `month_count` counts confirmed bookings with `check_in__year/month == booking.check_in`'s month, and campaign matching uses `start_date__lte=today, end_date__gte=today` against the same future `check_in`.

**Why it's a bug:** The "monthly repeat" multiplier (spec: ≥2 bookings *in the same calendar month*) is computed over check-in months, not booking/earn months. A guest booking two stays both checking in next March gets the multiplier even if booked months apart; conversely two bookings made the same week for different months miss it. The variable is even named `today` but holds a future date — misleading.

**Impact:** Multiplier (1.5×) applied incorrectly → over/under-crediting; campaign windows evaluated against the wrong date.

---

## LOY-08 — Coupon redemption is a dead contract
**Severity:** Medium
**Location:** `loyalty/models.py:83` (`COUPON_REDEMPTION`); `loyalty/views.py` (stub).

**Data flow:** `loyalty/views.py` is the Django default stub (`from django.shortcuts import render`), there is no `loyalty/urls.py`, and no code anywhere writes a `COUPON_REDEMPTION` ledger row or debits `loyalty_points` for a coupon. The spec describes guests redeeming points for discount coupons.

**Why it's a bug:** The redemption side of the ledger is declared but unimplemented. If redemption is added later against this code, the double-spend / negative-balance / expiry concerns (no `select_for_update`, see LOY-02) are unguarded by construction.

**Impact:** Feature gap today; latent double-spend risk the moment redemption is wired to the current non-atomic balance code.

---

## SET-01 — Hardcoded production DB credentials in base settings
**Severity:** Critical
**Location:** `hotel_booking/settings/base.py:106-115`.

**Data flow:**
```python
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.mysql',
    'NAME': 'ttr_v2', 'USER': 'root',
    'PASSWORD': 'vengeance',
    'HOST': '127.0.0.1', 'PORT': '3306',
}}
```
The DB password is a literal in a VCS-tracked file. The comment above even claims "Default to SQLite but allow override via DATABASE_URL" — but there is no `config('DATABASE_URL', ...)` here; it is fully hardcoded. (`prod.py:24-30` does override with `dj_database_url`, so prod escapes it, but dev and any base-only import use the plaintext root password.)

**Why it's a bug:** Secret committed to source control; `RAZORPAY_KEY_SECRET` is read via `config()` precisely to avoid this, so this is inconsistent and a real leak.

**Impact:** Anyone with repo access has the MySQL root password. Must be moved to env (`config('DATABASE_URL')`) and rotated.

---

## SET-02 — Insecure SECRET_KEY / DEBUG defaults
**Severity:** High
**Location:** `hotel_booking/settings/base.py:21-22`.

**Data flow:**
```python
SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me-in-production")
DEBUG = config("DEBUG", default=True, cast=bool)
```
`prod.py` forces `DEBUG = False` (line 7) but does **not** set or assert `SECRET_KEY`. If `SECRET_KEY` env var is absent in prod, the app silently boots with the public insecure default — no startup check.

**Why it's a bug:** Insecure secret + a `DEBUG=True` default means any environment that forgets to import `prod` (e.g. a stray `DJANGO_SETTINGS_MODULE` pointing at base, or a tool importing base directly) runs debug-on with a known signing key. Security-relevant defaults should fail closed.

**Impact:** Session/CSRF token forgery if the default key is ever used; info disclosure if DEBUG leaks. No guard prevents the insecure default in production.

---

## CORE-01 — WhatsApp task captures stale snapshot, no dedup on retry
**Severity:** Medium
**Location:** `payments/views.py:268,414` (`async_task('core.tasks.send_whatsapp_message', ...)`), `core/tasks.py:7`.

**Data flow:** Both confirmation paths enqueue the WhatsApp task with literal kwargs (name, reference, check_in) read at enqueue time. `Q_CLUSTER` sets `"retry": 120` (`base.py:303`) with no `ack_failures`/idempotency. `send_whatsapp_message` posts to Interakt; on a network timeout it returns `False` (caught), but django-q's retry can also re-run the task after `timeout` (60s) if it appears unacked.

**Why it's a bug:** (a) The task gets a value snapshot, not the booking pk, so if the booking is corrected (reference/tax recompute happens right after at lines 387-388 in the webhook path, *before* enqueue there but the verify path enqueues stale data) the message may carry pre-finalization values. (b) No external dedup key on the Interakt call, so a retry sends a duplicate confirmation. With LOY-01's dual paths, both verify and webhook enqueue a message → two WhatsApps.

**Impact:** Duplicate / stale booking-confirmation WhatsApp messages to guests.

---

## CORE-02 — Context processor tier can disagree with stored tier
**Severity:** Low
**Location:** `loyalty/context_processors.py:17-27`.

**Data flow:** The processor ignores `profile.loyalty_tier` (read at line 17 into `current_tier_name` but never used) and recomputes `current_tier` live from `LoyaltyTier` by points. Meanwhile templates elsewhere and `accounts/views.py:487` read the stored `profile.loyalty_tier`.

**Why it's a bug:** Two sources of truth for "current tier" — the live DB lookup here vs the persisted field set by the conflicting writers in LOY-03. They can show different tiers on different pages for the same user.

**Impact:** Inconsistent tier/discount display across the UI; minor but user-visible.

---

## Notes / non-findings
- No `from hotel_booking.settings.base import *` violations found outside the sanctioned `dev.py`/`prod.py` `from .base import *`.
- `Booking.status` `max_length=10` accommodates the longest choice (`confirmed`/`completed`/`cancelled` = 9). Service filters use the correct lowercase values — consistent.
- Background tasks correctly use `django_q.tasks.async_task` (not threading/celery), per stack rules.
