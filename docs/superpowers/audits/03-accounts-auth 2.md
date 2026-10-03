# Audit 03 — Accounts & Authentication Data-Flow

Scope: `accounts/` — email OTP, Google OAuth (django-allauth), account merge, custom user
model, auth middleware, permissions. Read-only audit. Date: 2026-06-17.

Files reviewed: `models.py`, `views.py`, `serializers.py`, `middleware.py`, `permissions.py`,
`utils.py`, `urls.py`, plus supporting `backends.py`, `managers.py`, `adapter.py`,
`role_routing.py`, and `hotel_booking/settings/base.py`.

## Summary

| ID | Severity | Title | Location |
|----|----------|-------|----------|
| AUTH-01 | Critical | OTP not bound to purpose/identity — any valid OTP completes any flow (forgot-password takeover) | `accounts/utils.py:66`, `accounts/views.py:636-651` |
| AUTH-02 | Critical | Google OAuth merge trusts unverified `extra_data['email']` — account takeover | `accounts/adapter.py:7-34` |
| AUTH-03 | Critical | OTP code compared with `!=` (non constant-time); no per-email send/verify rate limit | `accounts/utils.py:105`, `accounts/views.py:312-341` |
| AUTH-04 | High | `EmailBackend.authenticate` does not normalize email — case-variant login bypasses lockout & risks dup accounts | `accounts/backends.py:29-48` |
| AUTH-05 | High | Email-change OTP verify trusts client `email` field, not the cached pending email | `accounts/views.py:546-559` |
| AUTH-06 | High | `IsEmployee` permission rejects `super_admin`; `IsSuperAdmin` ignores `is_superuser` | `accounts/permissions.py:3-25` |
| AUTH-07 | High | CSRF disabled globally on all session-authenticated API endpoints | `accounts/backends.py:12-21` |
| AUTH-08 | Medium | `pre_social_login` activates inactive/revoked users on Google login (re-enables revoked staff) | `accounts/adapter.py:28-30` |
| AUTH-09 | Medium | Registration upsert deletes prior PendingRegistration with no rate limit — OTP-bombing / griefing | `accounts/views.py:82-91` |
| AUTH-10 | Medium | `get_user_profile` silently auto-creates/escalates profile to super_admin from `is_superuser`; broad `except Exception` | `accounts/role_routing.py:36-59` |
| AUTH-11 | Medium | Two concurrent registrations for same email can race past the active-user guard (no DB transaction/lock) | `accounts/views.py:253-280` |
| AUTH-12 | Low | OTP/Pending email uniqueness vs casing relies on callers; OTP table has no unique constraint on email | `accounts/models.py:98-100` |
| AUTH-13 | Low | Forgot-password leaves the verified OTP/session reusable; `pw_reset_verified` not cleared on failure paths | `accounts/views.py:654-681` |

---

## AUTH-01 — OTP is not bound to a purpose or to an authenticated subject (Critical)

**Location:** `accounts/utils.py:66` (`verify_otp`), consumed at `accounts/views.py:130`
(registration), `accounts/views.py:551` (email change), `accounts/views.py:645`
(forgot-password).

**Data flow:** A single `OTP` row keyed only by `email` is created by `create_and_store_otp`
(`utils.py:41`). `verify_otp(email, code)` looks up `OTP.objects.get(email=email)` with no
notion of *why* the code was issued. The same code therefore satisfies registration,
email-change, AND password reset. `forgot_password` (`views.py:618`) sends an OTP to any
**active** email; `forgot_password_verify` (`views.py:645`) accepts it and sets
`session['pw_reset_verified'] = True`, after which `forgot_password_set` (`views.py:654`)
resets the password.

**Why it's a bug:** OTPs are fungible across flows. If an attacker can induce an OTP to be
issued for a victim's email through *any* endpoint (e.g. the unauthenticated registration
endpoint at `views.py:82`, which issues an OTP for any email not already active, or
resend-otp), that same code — if intercepted/guessed — unlocks the password-reset flow.
There is no `purpose` column, no binding to the requesting session, and no binding to a
user id. Registration's `create_and_store_otp` and forgot-password's share one namespace.

**Impact:** Account takeover. Cross-purpose OTP reuse defeats the separation between "prove
you own a new email" and "reset the password of an existing account."

---

## AUTH-02 — Google OAuth merge trusts an unverified email claim (Critical)

**Location:** `accounts/adapter.py:7-34` (`pre_social_login`).

**Data flow:**
```python
email = sociallogin.account.extra_data['email'].lower()
user = User.objects.get(email=email)
sociallogin.connect(request, user)        # link Google identity to existing local account
if not user.is_active:
    user.is_active = True
    user.save(update_fields=['is_active'])
```
The merge keys solely on `extra_data['email']`. There is **no check of
`extra_data.get('email_verified')`**. `SOCIALACCOUNT_PROVIDERS['google']`
(`settings/base.py:141`) requests only `profile`/`email` scope and sets no
`EMAIL_AUTHENTICATION`/verified-email requirement.

**Why it's a bug:** `sociallogin.connect()` auto-links the Google identity to a pre-existing
local (email+password) account whenever the email strings match. If a Google account presents
an email it has not proven ownership of (or a provider/edge case yields an unverified email),
the attacker's Google login is merged into the victim's existing local account — inheriting
its bookings, loyalty points, and role. The victim's data "wins" but the attacker gains a
logged-in session as the victim. The merge happens **before** any local verification.

**Impact:** Full account takeover of any local account whose email an attacker can assert
through Google. Critical because account merge is explicitly a documented feature and this is
the merge's trust boundary.

---

## AUTH-03 — Non constant-time OTP comparison + no send/verify rate limiting (Critical)

**Location:** `accounts/utils.py:105` (`if submitted_code != otp.code:`); resend at
`accounts/views.py:312-341`; OTP issuance at `accounts/views.py:82-91`.

**Data flow:** OTP generation is sound (`secrets.randbelow`, `utils.py:27`). Verification
compares with the plain `!=` operator (`utils.py:105`) rather than
`secrets.compare_digest`/`hmac.compare_digest`. Per-OTP brute force is bounded by
`OTP_MAX_ATTEMPTS=3` (`is_blocked`, `models.py:127`), **but**:
- `ResendOTPView` (`views.py:312`) and `RegisterView` (`views.py:82`) call
  `create_and_store_otp`, which **deletes the old OTP and its attempt counter**
  (`utils.py:50`) and issues a fresh code with `attempts=0`. There is no throttle on how
  often a caller may request a new code.

**Why it's a bug:** An attacker can defeat the 3-attempt lock by repeatedly resending: each
resend resets `attempts` to 0, giving unlimited 3-guess windows against a fixed 6-digit space.
Combined with no IP/email send throttle, this is an online brute-force of a 6-digit OTP. The
`!=` comparison is a secondary timing-side-channel concern.

**Impact:** OTP brute-force / bypass → email "verification" forgeable → registration or
password-reset takeover. (Note `dev.py:17` raises `LOGIN_MAX_ATTEMPTS` to 20, but OTP has no
equivalent ceiling at all.)

---

## AUTH-04 — Login backend does not normalize email (High)

**Location:** `accounts/backends.py:29-48` (`EmailBackend.authenticate`).

**Data flow:** `LoginSerializer.validate_email` (`serializers.py:147`) lowercases/strips, so
the *API* path is normalized. But `EmailBackend.authenticate` does `User.objects.get(email=email)`
on the **raw** argument with no `normalize_email`. Lockout tracking
(`check_login_lock`/`record_failed_login`, `utils.py:125,143`) normalizes its key, while the
backend lookup does not.

**Why it's a bug:** Any caller of `authenticate()` that passes a non-normalized email (other
backends, future code, or a direct call) bypasses the normalized lockout bucket. More broadly,
the `User.email` column has no case-insensitive constraint (`models.py:31`), so
`Foo@x.com` and `foo@x.com` are distinct rows; registration normalizes but the login backend
does not, creating inconsistent identity resolution across the auth surface.

**Impact:** Lockout-throttle evasion and potential duplicate/mismatched account resolution.

---

## AUTH-05 — Email-change OTP verify trusts the client-supplied email (High)

**Location:** `accounts/views.py:546-559` (`update_profile`, `field == 'email_verify'`).

**Data flow:**
```python
new_email = data.get('email', '').strip().lower()
if not cache.get(f'email_change:{user.pk}:{new_email}'): ...
result = verify_otp(new_email, otp)
...
user.email = new_email
```
The cache guard ties `{user.pk}:{new_email}` to the request that *initiated* the change
(`email_request`, `views.py:543`). That part is sound. However `verify_otp(new_email, otp)`
resolves the OTP purely by email (see AUTH-01). Because OTPs are not purpose-bound, any valid
OTP that happens to exist for `new_email` — e.g. one issued because the attacker started a
*registration* for that address — verifies here.

**Why it's a bug:** Combined with AUTH-01, the email-change confirmation can be satisfied by
an OTP minted in a different flow. The cache key proves the logged-in user *requested* the
change, but the OTP itself is not scoped to this user or this purpose.

**Impact:** Weakens the email-change verification; with AUTH-01 enables changing one's account
email to an address the OTP was issued for under another flow.

---

## AUTH-06 — Permission classes read the wrong role authority (High)

**Location:** `accounts/permissions.py:3-25`.

**Data flow:**
```python
class IsEmployee:    role == 'employee_admin'   # rejects 'employee' AND 'super_admin'
class IsSuperAdmin:  role == 'super_admin'       # ignores user.is_superuser
```
Everywhere else in the codebase, super-admin authority is derived from BOTH the profile role
and `is_superuser`: `role_routing.get_user_role` (`role_routing.py:56`) returns
`super_admin` whenever `is_superuser` is true, and middleware treats `is_superuser` as the
Django-admin gate (`middleware.py:98-102`).

**Why it's a bug:** Two inconsistencies. (1) `IsSuperAdmin` (used by `CreateEmployeeView`,
`views.py:571`) checks only `userprofile.role == 'super_admin'`. A Django superuser whose
`UserProfile.role` is stale (e.g. `guest`, the default at `models.py:248`) is **denied**
employee creation even though `get_user_role` would treat them as super_admin everywhere
else — and conversely a profile flipped to `super_admin` without `is_superuser` passes. The
two authorities can disagree. (2) `IsEmployee` requires exactly `employee_admin`, so a plain
`employee` and a `super_admin` both fail it — a super_admin cannot use employee-scoped APIs,
contradicting the "Super Admin controls everything" model in CLAUDE.md.

**Impact:** Inconsistent authorization: legitimate super admins blocked from APIs, and the
role-vs-`is_superuser` divergence is a latent privilege-mismatch bug. Should derive from
`get_user_role(request.user)` like the rest of the system.

---

## AUTH-07 — CSRF protection disabled on all session-authenticated APIs (High)

**Location:** `accounts/backends.py:12-21` (`CsrfExemptSessionAuthentication.enforce_csrf`
returns unconditionally).

**Data flow:** DRF's `SessionAuthentication` enforces CSRF for cookie/session-authenticated
browser requests. This subclass overrides `enforce_csrf` to a no-op. If wired as a default
authentication class (it exists specifically to be used), every session-authenticated POST
(login, set-password, employee creation, logout) is exposed to cross-site requests using the
victim's session cookie.

**Why it's a bug:** Session auth without CSRF means a malicious site can drive state-changing
POSTs (e.g. `CreateEmployeeView`, password/email changes) as the logged-in victim. The
docstring justifies it for "Postman/terminal testing," but that should not ship as the
production default.

**Impact:** Cross-site request forgery against authenticated guests and admins.

---

## AUTH-08 — Google login re-activates inactive/revoked accounts (Medium)

**Location:** `accounts/adapter.py:28-30`.

**Data flow:** On Google login matching an existing email, `if not user.is_active: user.is_active = True`.
`UserProfile.revoke()` (`models.py:282`) soft-disables staff by setting `is_active=False`.

**Why it's a bug:** A revoked employee/admin whose account email matches a Google login is
silently re-activated (`is_active=True`) on next Google sign-in, with no check of
`userprofile.is_revoked`. Revocation is bypassed.

**Impact:** A revoked staff member can regain an active account via Google OAuth, undoing the
audit-preserving soft-revoke.

---

## AUTH-09 — Unthrottled registration upsert enables OTP bombing (Medium)

**Location:** `accounts/views.py:82-91` (`RegisterView.post`).

**Data flow:** For any email not already `is_active`, the view unconditionally deletes any
existing `PendingRegistration` and creates a new one, then issues + emails an OTP — with no
rate limiting and `permission_classes = [AllowAny]`.

**Why it's a bug:** An attacker can repeatedly POST a victim's email, mailbombing them with
OTP emails and (per AUTH-03) resetting attempt counters. Also wipes any in-progress pending
record for that email.

**Impact:** Email-flooding/griefing of arbitrary addresses; amplifies AUTH-03.

---

## AUTH-10 — Implicit profile creation / role escalation with broad except (Medium)

**Location:** `accounts/role_routing.py:36-59` (`get_user_profile`).

**Data flow:** On any exception accessing `user.userprofile` (`except Exception:`), the code
`get_or_create`s a profile, defaulting role to `super_admin` when `is_superuser` else `guest`.
It also *persists* a role flip to `super_admin` for any `is_superuser` user (`role_routing.py:43-45`).

**Why it's a bug:** (1) `except Exception` swallows unrelated DB errors and masks them as a
"missing profile," writing a new row as a side effect of a read-path helper invoked from
middleware on every request. (2) Auto-creating a `super_admin` profile from `is_superuser`
couples two authorities and mutates data during request routing. A read helper should not have
write side effects on every request.

**Impact:** Hidden writes on the hot path, error masking, and role authority coupling that
makes AUTH-06's inconsistency harder to reason about.

---

## AUTH-11 — Race between concurrent same-email registrations (Medium)

**Location:** `accounts/views.py:253-280` (`SetPasswordView`), and `serializers.py:43`
active-user guard.

**Data flow:** The "already active?" check (`User.objects.filter(email=email).first()`,
`views.py:253`) and the subsequent `create_user`/adopt are not wrapped in a transaction or
`select_for_update`. `email` is unique at the DB level (`models.py:31`), so a true duplicate
INSERT would raise `IntegrityError` — but that error is **unhandled** here, surfacing as an
unhandled 500 and potentially a half-applied state (PendingRegistration deleted, no clean
response).

**Why it's a bug:** Two near-simultaneous completions for the same email (or completion racing
with another path that creates the user) hit an uncaught `IntegrityError`. No
`transaction.atomic` / `get_or_create` guard.

**Impact:** 500 errors and inconsistent half-created state under concurrency; no graceful
"please log in" path on the race.

---

## AUTH-12 — OTP table lacks email uniqueness; normalization is caller-dependent (Low)

**Location:** `accounts/models.py:98-100` (`OTP.email` is `db_index=True` but not `unique`).

**Data flow:** `verify_otp` does `OTP.objects.get(email=email)` (`utils.py:79`), which assumes
at most one row per email. `create_and_store_otp` deletes prior rows first, but nothing at the
schema level enforces it; a concurrent issue could create two rows and make `.get()` raise
`MultipleObjectsReturned` (unhandled). `User.email` likewise has no case-insensitive
uniqueness — normalization lives only in serializers/utils, not the DB.

**Impact:** Latent `MultipleObjectsReturned`/duplicate-identity edge cases; defense-in-depth gap.

---

## AUTH-13 — Forgot-password verified flag/OTP not reliably cleared (Low)

**Location:** `accounts/views.py:636-681`.

**Data flow:** `verify_otp` deletes the OTP on success (`utils.py:117`), good. But
`pw_reset_verified` is set in session (`views.py:647`) and only popped on the success branch
of `forgot_password_set` (`views.py:675-676`). If the user abandons after verifying, the
session retains `pw_reset_verified=True` and `pw_reset_email`, so any later GET of
`forgot-password/set/` lets them set a new password without re-proving the OTP (the OTP itself
is already consumed, so identity is no longer re-checked).

**Impact:** A stale verified session can complete a password reset later without a fresh OTP,
widening the reset window on shared/persisted sessions.

---

## Notes / confirmed-safe

- OTP generation uses `secrets.randbelow` over the full 6-digit range — randomness is fine
  (`utils.py:27`).
- Successful OTP is deleted, preventing trivial single-code reuse *within one flow*
  (`utils.py:117`) — the reuse risk is cross-flow (AUTH-01), not intra-flow.
- `EmailBackend` runs a dummy hash on missing users to blunt timing enumeration
  (`backends.py:42-44`).
- `LoginAttempt.is_locked` auto-reset side effect was previously reviewed and is safe
  (`models.py:213`).
