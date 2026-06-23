# Security Foundations — Design Spec

**Date:** 2026-06-17
**Scope:** TTR-V2 · Phase 1 of audit remediation
**Findings addressed:** SET-01, SET-02, AUTH-01, AUTH-02, AUTH-03, ADM-01, ADM-02
**Findings deferred:** All Medium/Low; Data Consistency phase (AUTH-04, AUTH-06, AUTH-07, LOY-03/04, BSF-03/04/05, ADM-03) handled separately.

---

## Context

The internal data-flow audit (docs/superpowers/audits/00-MASTER-dataflow-audit.md) identified 10 Critical and 16 High findings. This spec addresses the 7 that are pre-conditions for everything else: hardcoded credentials that leak regardless of other fixes, OTP security gaps that enable account takeover, and an authorization hole in super-admin employee management that allows privilege escalation.

Deployment context: basic VPS, Django 6, MySQL, <500 req/week. No Redis. Django's built-in cache backend is sufficient for all rate-limiting needs here.

---

## Cluster 1 — Settings / Credentials

### SET-01: Remove hardcoded DB credentials from base.py

**Problem:** `hotel_booking/settings/base.py` has a fully literal `DATABASES` block with MySQL root password `'vengeance'` committed to VCS. `prod.py` overrides it with `dj_database_url`, but `base.py` is the fallback and the leak is already in git history.

**Fix:**

Replace the literal `DATABASES` block in `base.py` with a `dj_database_url` call with a safe SQLite default:

```python
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        env='DATABASE_URL',
        default='sqlite:///db.sqlite3',
    )
}
```

Add `DATABASE_URL=sqlite:///db.sqlite3` to `.env.example` so dev setup is documented.

`prod.py` already calls `dj_database_url.config(env='DATABASE_URL')` — leave it unchanged. Production must set `DATABASE_URL` in the server environment; the hardcoded MySQL block is gone.

**Ops note (out of scope for code, must be done manually):** The password `vengeance` is in git history. Once code is deployed, rotate the MySQL root password on the VCS and update the server's `DATABASE_URL` env var. This spec covers only the code change.

**Files:** `hotel_booking/settings/base.py`, `.env.example`
**Migration:** None

---

### SET-02: Fail-closed on missing SECRET_KEY in production

**Problem:** `base.py` defaults `SECRET_KEY` to a public insecure string. `prod.py` sets `DEBUG = False` but never asserts `SECRET_KEY`. If `SECRET_KEY` env var is absent in production, the app boots silently on the known-insecure default.

**Fix — two sub-changes:**

1. **`base.py`:** Flip `DEBUG` default from `True` to `False`. Anyone who needs debug must set `DEBUG=True` explicitly in their env. This is the safe default direction.

   ```python
   DEBUG = config("DEBUG", default=False, cast=bool)
   ```

2. **`prod.py`:** Add a startup guard at the top of the file (after `from .base import *`) that raises `ImproperlyConfigured` if `SECRET_KEY` is still the insecure default:

   ```python
   from django.core.exceptions import ImproperlyConfigured

   _INSECURE_DEFAULT = "django-insecure-change-me-in-production"
   if SECRET_KEY == _INSECURE_DEFAULT:
       raise ImproperlyConfigured(
           "SECRET_KEY must be set to a secure value in production. "
           "Set the SECRET_KEY environment variable."
       )
   ```

   This fails the process at startup — before any request is served — if the key is missing or still default.

**Files:** `hotel_booking/settings/base.py`, `hotel_booking/settings/prod.py`
**Migration:** None

---

## Cluster 2 — OTP Security

### AUTH-01: Bind OTP to its purpose (prevent cross-flow reuse)

**Problem:** A single `OTP` row is keyed only by `email`. The same code satisfies registration, password-reset, and email-change flows. An OTP issued by the unauthenticated registration endpoint can be used to complete a password reset → account takeover.

**Fix — add `purpose` column to `OTP` model:**

New field:
```python
PURPOSE_REGISTRATION   = 'registration'
PURPOSE_PASSWORD_RESET = 'password_reset'
PURPOSE_EMAIL_CHANGE   = 'email_change'

PURPOSE_CHOICES = [
    (PURPOSE_REGISTRATION,   'Registration'),
    (PURPOSE_PASSWORD_RESET, 'Password Reset'),
    (PURPOSE_EMAIL_CHANGE,   'Email Change'),
]

purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
```

**`create_and_store_otp(email, purpose)` changes:**
- Delete only `OTP.objects.filter(email=email, purpose=purpose)` — not all OTPs for that email. A concurrent password-reset code is not wiped when a new registration code is issued.
- Create new OTP with `purpose=purpose`.

**`verify_otp(email, code, purpose)` changes:**
- Lookup: `OTP.objects.get(email=email, purpose=purpose)`. A registration code cannot satisfy a password-reset lookup — wrong purpose → `OTP.DoesNotExist` → verification fails.

**Callers to update:**

| View | Purpose constant to pass |
|------|--------------------------|
| `RegisterView.post` | `PURPOSE_REGISTRATION` |
| `ResendOTPView.post` | `PURPOSE_REGISTRATION` |
| `SetPasswordView.post` (OTP verify step) | `PURPOSE_REGISTRATION` |
| `ForgotPasswordView.post` | `PURPOSE_PASSWORD_RESET` |
| `ForgotPasswordVerifyView.post` | `PURPOSE_PASSWORD_RESET` |
| `update_profile` (`field == 'email_verify'`) | `PURPOSE_EMAIL_CHANGE` |
| `update_profile` (`field == 'email_request'`) | `PURPOSE_EMAIL_CHANGE` |

**Files:** `accounts/models.py`, `accounts/utils.py`, `accounts/views.py`
**Migration:** 1 — add `purpose` column. Existing rows in dev can be deleted or given a default; prod should have no live OTP rows at migration time (they expire quickly).

---

### AUTH-02: Block Google OAuth merge on unverified email

**Problem:** `pre_social_login` in `accounts/adapter.py` merges a Google identity into an existing local account by matching email strings alone. There is no check that Google has verified the email claim. An attacker presenting an unverified email can take over the matching local account.

**Fix:**

In `adapter.py:pre_social_login`, add a verified-email guard before the merge:

```python
def pre_social_login(self, request, sociallogin):
    if sociallogin.is_existing:
        return

    # Guard: only merge on a Google-verified email
    if not sociallogin.account.extra_data.get('email_verified', False):
        from allauth.exceptions import ImmediateHttpResponse
        from django.http import HttpResponse
        raise ImmediateHttpResponse(
            HttpResponse(
                "Your Google account email is not verified. "
                "Please verify your email with Google before signing in.",
                status=400,
                content_type='text/plain',
            )
        )

    # existing merge logic continues unchanged below
    try:
        email = sociallogin.account.extra_data['email'].lower()
        user = User.objects.get(email=email)
        ...
```

If `email_verified` is absent or `False`, login is blocked before any merge or activation. Google's own OAuth flow sets `email_verified: true` for standard Gmail accounts; only edge-case/workspace configurations would ever hit this block in practice.

**Files:** `accounts/adapter.py`
**Migration:** None

---

### AUTH-03: OTP send throttle + constant-time comparison

**Problem (two sub-issues):**

1. `verify_otp` compares OTP codes with `!=` (timing side channel).
2. `ResendOTPView` and `RegisterView` both call `create_and_store_otp`, which resets the attempt counter. An attacker can call resend repeatedly, getting unlimited 3-guess windows against a 6-digit OTP.

**Fix — two sub-changes:**

**A. Constant-time comparison** in `accounts/utils.py:verify_otp`:

```python
import hmac

# Before:
if submitted_code != otp.code:

# After:
if not hmac.compare_digest(str(submitted_code), str(otp.code)):
```

**B. Per-email send throttle** added at the top of `create_and_store_otp`:

```python
from django.core.cache import cache

OTP_SEND_LIMIT     = 5       # max sends per window
OTP_SEND_WINDOW    = 3600    # 1-hour window in seconds

def _check_otp_send_throttle(email: str) -> bool:
    """Returns True if the send is allowed, False if throttled."""
    key = f'otp_send:{email}'
    count = cache.get(key, 0)
    if count >= OTP_SEND_LIMIT:
        return False
    cache.set(key, count + 1, timeout=OTP_SEND_WINDOW)
    return True
```

Call `_check_otp_send_throttle(email)` at the start of `create_and_store_otp`. If throttled, raise a `ValidationError` (or return a sentinel) — callers (`RegisterView`, `ResendOTPView`, `ForgotPasswordView`) return a `429` response.

Limit: 5 sends per hour per email. Appropriate for a hotel app (<500 req/week); blocks automated bombing while allowing genuine resends.

No new dependency — uses Django's built-in `CACHES` (memory or DB backend as configured).

**Files:** `accounts/utils.py`
**Migration:** None

---

## Cluster 3 — Admin Authorization

### ADM-01: Scope employee management endpoints to actual employees

**Problem:** `employee_update`, `employee_delete`, and `reset_password` in `superadmin/views.py` look up `User` by raw pk with no role filter. A super-admin can target another super-admin (or any guest) through these endpoints — resetting their password, locking their account, or revoking them.

**Fix:**

Change every unscoped `User` lookup in the employee management block from:

```python
employee = get_object_or_404(User, pk=user_id)
```

to:

```python
employee = get_object_or_404(User, pk=user_id, userprofile__role='employee')
```

This makes non-employee users invisible to the endpoint — they return 404. The self-protect guard (`employee == request.user`) remains but is no longer the only line of defence.

Applies to three functions: `employee_update` (line 197), `employee_delete` (line 258), and the `reset_password` action branch (line 228 — inside `employee_update`, so covered by the same change at 197).

**Files:** `superadmin/views.py`
**Migration:** None

---

### ADM-02: Allowlist fin_level; validate property assignment

**Problem:** `fin_level` (financial access tier A/B/C) is written verbatim from POST data with no validation. Property assignment is also untrusted. Target is any `User` (ADM-01 fixes the scope; this fixes the value validation).

**Fix — two sub-changes:**

**A. `fin_level` allowlist:**

Add a constant and a guard in both `employee_create` and the `update_fin` action branch:

```python
FIN_LEVEL_CHOICES = frozenset({'A', 'B', 'C'})

fin_level = request.data.get('fin_level', 'C')
if fin_level not in FIN_LEVEL_CHOICES:
    return JsonResponse({'error': 'Invalid financial level. Must be A, B, or C.'}, status=400)
```

**B. Property ID validation:**

Before calling `.set()`, verify submitted property IDs are real:

```python
property_ids = request.data.get('property_ids', [])
valid_properties = Property.objects.filter(id__in=property_ids)
if valid_properties.count() != len(property_ids):
    return JsonResponse({'error': 'One or more property IDs are invalid.'}, status=400)
profile.assigned_properties.set(valid_properties)
```

This replaces the current silent `.set(Property.objects.filter(...))` which drops unknown IDs with no feedback.

**Files:** `superadmin/views.py`
**Migration:** None

---

## Summary

| Finding | Files Changed | Migration |
|---------|--------------|-----------|
| SET-01 | `settings/base.py`, `.env.example` | No |
| SET-02 | `settings/base.py`, `settings/prod.py` | No |
| AUTH-01 | `accounts/models.py`, `accounts/utils.py`, `accounts/views.py` | Yes — 1 migration |
| AUTH-02 | `accounts/adapter.py` | No |
| AUTH-03 | `accounts/utils.py` | No |
| ADM-01 | `superadmin/views.py` | No |
| ADM-02 | `superadmin/views.py` | No |

**Total:** 6 files + 1 migration file. No new dependencies. No new tables beyond the `purpose` column.

---

## Testing Checklist

- [ ] `python manage.py migrate` runs cleanly with the new `purpose` column
- [ ] Registration OTP cannot satisfy the forgot-password verify endpoint
- [ ] 6th OTP send for same email within 1 hour returns 429
- [ ] Google login with `email_verified: false` returns 400 (can mock `extra_data` in test)
- [ ] `employee_update` with a super-admin UUID returns 404
- [ ] `employee_update` with `fin_level='X'` returns 400
- [ ] `employee_update` with invalid property ID returns 400
- [ ] Dev server boots with `DATABASE_URL` env var (SQLite path)
- [ ] `prod.py` import raises `ImproperlyConfigured` when `SECRET_KEY` is missing
- [ ] `DEBUG` defaults to `False` when env var not set
