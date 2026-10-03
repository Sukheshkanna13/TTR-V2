# Security Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 7 Critical/High security findings (SET-01, SET-02, AUTH-01, AUTH-02, AUTH-03, ADM-01, ADM-02) with zero new dependencies and one DB migration.

**Architecture:** Three independent clusters executed in order — credentials first (no migration, highest blast radius), OTP security second (one migration + logic), admin authorization third (logic only). Each task is independently testable and committable.

**Tech Stack:** Django 6, Django TestCase (not pytest), `python manage.py test`, Django cache (memory backend in tests), `hmac.compare_digest` from stdlib.

## Global Constraints

- No new pip dependencies — use stdlib `hmac`, Django cache, `dj_database_url` (already installed)
- All tests use `django.test.TestCase` and `self.client` — match the style in `accounts/tests.py`
- Run tests with: `python manage.py test <app>` from the repo root with venv active
- Commits use lowercase imperative subject lines, no co-author trailers needed
- Migration must be named `0007_otp_purpose.py` (accounts app is currently at `0006_...`)
- Never use `pytest` — this project uses Django's test runner

---

## File Map

| File | Change |
|------|--------|
| `hotel_booking/settings/base.py` | Replace hardcoded DATABASES; flip DEBUG default |
| `hotel_booking/settings/prod.py` | Add SECRET_KEY startup guard |
| `.env.example` | Uncomment DATABASE_URL SQLite default |
| `accounts/models.py` | Add `purpose` field + constants to OTP model |
| `accounts/migrations/0007_otp_purpose.py` | Generated migration for purpose column |
| `accounts/utils.py` | Add throttle helper; update `create_and_store_otp` + `verify_otp` signatures |
| `accounts/views.py` | Update all 7 OTP call sites with purpose constants |
| `accounts/adapter.py` | Add `email_verified` guard before OAuth merge |
| `superadmin/views.py` | Scope employee lookups to role=employee; allowlist fin_level |
| `accounts/tests.py` | New test classes for OTP purpose, throttle, constant-time |
| `superadmin/tests.py` | New test class for ADM-01/ADM-02 guards |

---

## Task 1: Credentials — Remove hardcoded DB password, harden SECRET_KEY (SET-01, SET-02)

**Files:**
- Modify: `hotel_booking/settings/base.py:22,106-115`
- Modify: `hotel_booking/settings/prod.py:4-7`
- Modify: `.env.example`

**Interfaces:**
- Produces: `base.py` DATABASES reads from `DATABASE_URL` env var; `prod.py` raises `ImproperlyConfigured` on insecure key

- [ ] **Step 1: Replace the hardcoded DATABASES block in base.py**

Open `hotel_booking/settings/base.py`. Replace lines 105-115:

```python
# Default to SQLite but allow override via DATABASE_URL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'ttr_v2',
        'USER': 'root',
        'PASSWORD': 'vengeance',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    }
}
```

with:

```python
# Read from DATABASE_URL env var; defaults to SQLite in dev
DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        default="sqlite:///db.sqlite3",
    )
}
```

`dj_database_url` is already imported at line 9 of `base.py`. No new import needed.

- [ ] **Step 2: Flip DEBUG default to False in base.py**

On line 22, change:

```python
DEBUG = config("DEBUG", default=True, cast=bool)
```

to:

```python
DEBUG = config("DEBUG", default=False, cast=bool)
```

- [ ] **Step 3: Add SECRET_KEY startup guard to prod.py**

Open `hotel_booking/settings/prod.py`. After line 4 (`from .base import *`), insert:

```python
from django.core.exceptions import ImproperlyConfigured

_INSECURE_KEY = "django-insecure-change-me-in-production"
if SECRET_KEY == _INSECURE_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY must be set to a secure value in production. "
        "Set the SECRET_KEY environment variable."
    )
```

- [ ] **Step 4: Update .env.example to document DATABASE_URL**

Open `.env.example`. The DATABASE_URL section currently reads:

```
# Leave blank in dev — SQLite is used automatically
# In production, set to your PostgreSQL URL:
# DATABASE_URL=postgres://user:password@host:5432/dbname
```

Replace with:

```
# Dev: SQLite (default — no server needed)
DATABASE_URL=sqlite:///db.sqlite3
# Production: uncomment and set your PostgreSQL URL:
# DATABASE_URL=postgres://user:password@host:5432/dbname
```

- [ ] **Step 5: Verify dev server still boots**

```bash
DATABASE_URL=sqlite:///db.sqlite3 DEBUG=True python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Verify prod guard fires correctly**

```bash
python -c "
import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'hotel_booking.settings.prod'
os.environ['DATABASE_URL'] = 'sqlite:///db.sqlite3'
# SECRET_KEY intentionally absent — should raise
try:
    django.setup()
    print('FAIL: no error raised')
except Exception as e:
    print('PASS:', type(e).__name__, str(e)[:80])
"
```

Expected output: `PASS: ImproperlyConfigured SECRET_KEY must be set...`

- [ ] **Step 7: Commit**

```bash
git add hotel_booking/settings/base.py hotel_booking/settings/prod.py .env.example
git commit -m "fix(settings): remove hardcoded DB creds; fail-closed on insecure SECRET_KEY"
```

---

## Task 2: OTP Model — Add purpose column (AUTH-01, schema only)

**Files:**
- Modify: `accounts/models.py:85-137`
- Create: `accounts/migrations/0007_otp_purpose.py`

**Interfaces:**
- Produces: `OTP.PURPOSE_REGISTRATION = 'registration'`, `OTP.PURPOSE_PASSWORD_RESET = 'password_reset'`, `OTP.PURPOSE_EMAIL_CHANGE = 'email_change'`; `OTP.purpose` CharField; migration `0007_otp_purpose`

- [ ] **Step 1: Write the failing test**

In `accounts/tests.py`, add a new test class at the bottom of the file:

```python
class OTPPurposeModelTests(TestCase):
    def test_otp_created_with_purpose(self):
        from accounts.models import OTP
        otp = OTP.objects.create(
            email="test@example.com",
            code="123456",
            purpose=OTP.PURPOSE_REGISTRATION,
        )
        self.assertEqual(otp.purpose, "registration")

    def test_otp_purpose_constants_exist(self):
        from accounts.models import OTP
        self.assertEqual(OTP.PURPOSE_REGISTRATION, "registration")
        self.assertEqual(OTP.PURPOSE_PASSWORD_RESET, "password_reset")
        self.assertEqual(OTP.PURPOSE_EMAIL_CHANGE, "email_change")
```

- [ ] **Step 2: Run test — expect failure**

```bash
python manage.py test accounts.tests.OTPPurposeModelTests -v 2
```

Expected: FAIL — `TypeError: OTP() got an unexpected keyword argument 'purpose'` or `AttributeError: type object 'OTP' has no attribute 'PURPOSE_REGISTRATION'`

- [ ] **Step 3: Add purpose field and constants to OTP model**

Open `accounts/models.py`. In the `OTP` class, add the constants and field. After line 91 (the class docstring), insert the purpose constants. Then add the `purpose` field after the `code` field (after line 103):

```python
class OTP(models.Model):
    """
    OTP model — stores verification codes directly in PostgreSQL.

    Each OTP is tied to a user's email + purpose, has a 6-digit code,
    tracks attempts, and expires after a configurable duration.
    """

    PURPOSE_REGISTRATION   = "registration"
    PURPOSE_PASSWORD_RESET = "password_reset"
    PURPOSE_EMAIL_CHANGE   = "email_change"

    PURPOSE_CHOICES = [
        (PURPOSE_REGISTRATION,   "Registration"),
        (PURPOSE_PASSWORD_RESET, "Password Reset"),
        (PURPOSE_EMAIL_CHANGE,   "Email Change"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email = models.EmailField(
        db_index=True,
    )
    purpose = models.CharField(
        max_length=20,
        choices=PURPOSE_CHOICES,
        default=PURPOSE_REGISTRATION,
    )
    code = models.CharField(
        max_length=6,
    )
    attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of failed verification attempts.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "OTP"
        verbose_name_plural = "OTPs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP({self.purpose}) for {self.email} (expires {self.expires_at})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_blocked(self):
        max_attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 3)
        return self.attempts >= max_attempts

    def save(self, *args, **kwargs):
        if not self.expires_at:
            expiry_minutes = getattr(settings, "OTP_EXPIRY_MINUTES", 10)
            self.expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
        super().save(*args, **kwargs)
```

- [ ] **Step 4: Generate the migration**

```bash
python manage.py makemigrations accounts --name otp_purpose
```

Expected: `accounts/migrations/0007_otp_purpose.py` created.

- [ ] **Step 5: Apply migration**

```bash
python manage.py migrate accounts
```

Expected: `Applying accounts.0007_otp_purpose... OK`

- [ ] **Step 6: Run test — expect pass**

```bash
python manage.py test accounts.tests.OTPPurposeModelTests -v 2
```

Expected: `OK` — 2 tests pass.

- [ ] **Step 7: Commit**

```bash
git add accounts/models.py accounts/migrations/0007_otp_purpose.py
git commit -m "feat(accounts): add purpose field to OTP model (AUTH-01)"
```

---

## Task 3: OTP Utils — Purpose binding + send throttle + constant-time compare (AUTH-01, AUTH-03)

**Files:**
- Modify: `accounts/utils.py:41-118`

**Interfaces:**
- Consumes: `OTP.PURPOSE_REGISTRATION`, `OTP.PURPOSE_PASSWORD_RESET`, `OTP.PURPOSE_EMAIL_CHANGE` from Task 2
- Produces:
  - `create_and_store_otp(email: str, purpose: str) -> str` — raises `ValueError("OTP send limit reached")` when throttled
  - `verify_otp(email: str, submitted_code: str, purpose: str) -> dict` — same return shape as before `{"success": bool, "error": str|None, "code": str|None}`
  - `_check_otp_send_throttle(email: str) -> bool` — internal helper, returns `True` if allowed

- [ ] **Step 1: Write the failing tests**

In `accounts/tests.py`, add:

```python
class OTPUtilsTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_create_and_store_otp_requires_purpose(self):
        from accounts.utils import create_and_store_otp
        import inspect
        sig = inspect.signature(create_and_store_otp)
        self.assertIn("purpose", sig.parameters)

    def test_verify_otp_wrong_purpose_fails(self):
        from accounts.models import OTP
        from accounts.utils import create_and_store_otp, verify_otp
        create_and_store_otp("a@example.com", OTP.PURPOSE_REGISTRATION)
        result = verify_otp("a@example.com", "000000", OTP.PURPOSE_PASSWORD_RESET)
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "OTP_NOT_FOUND")

    def test_verify_otp_correct_purpose_succeeds(self):
        from accounts.models import OTP
        from accounts.utils import create_and_store_otp, verify_otp
        code = create_and_store_otp("b@example.com", OTP.PURPOSE_REGISTRATION)
        result = verify_otp("b@example.com", code, OTP.PURPOSE_REGISTRATION)
        self.assertTrue(result["success"])

    def test_otp_send_throttle_blocks_after_limit(self):
        from accounts.models import OTP
        from accounts.utils import create_and_store_otp
        email = "throttle@example.com"
        for _ in range(5):
            create_and_store_otp(email, OTP.PURPOSE_REGISTRATION)
        with self.assertRaises(ValueError):
            create_and_store_otp(email, OTP.PURPOSE_REGISTRATION)
```

- [ ] **Step 2: Run tests — expect failure**

```bash
python manage.py test accounts.tests.OTPUtilsTests -v 2
```

Expected: FAIL — `TypeError: create_and_store_otp() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Rewrite create_and_store_otp and verify_otp in utils.py**

Open `accounts/utils.py`. Replace the two OTP database operation functions (lines 41-118) with:

```python
# =============================================================================
# OTP SEND THROTTLE
# =============================================================================

OTP_SEND_LIMIT  = 5     # max sends per window per email
OTP_SEND_WINDOW = 3600  # 1-hour window in seconds


def _check_otp_send_throttle(email: str) -> bool:
    """Return True if send is allowed; False if the hourly limit is reached."""
    from django.core.cache import cache
    key = f"otp_send:{email}"
    count = cache.get(key, 0)
    if count >= OTP_SEND_LIMIT:
        return False
    cache.set(key, count + 1, timeout=OTP_SEND_WINDOW)
    return True


# =============================================================================
# OTP DATABASE OPERATIONS
# =============================================================================

def create_and_store_otp(email: str, purpose: str) -> str:
    """
    Generate a new OTP for (email, purpose), store it, return the code.
    Raises ValueError if the send throttle is exceeded.
    Deletes any existing OTP for the same (email, purpose) only.
    """
    from .models import OTP
    email = normalize_email(email)

    if not _check_otp_send_throttle(email):
        raise ValueError("OTP send limit reached. Try again in an hour.")

    OTP.objects.filter(email=email, purpose=purpose).delete()

    otp_code = generate_otp()
    expiry_minutes = getattr(settings, "OTP_EXPIRY_MINUTES", 10)
    expires_at = timezone.now() + timedelta(minutes=expiry_minutes)

    OTP.objects.create(
        email=email,
        purpose=purpose,
        code=otp_code,
        expires_at=expires_at,
    )

    return otp_code


def verify_otp(email: str, submitted_code: str, purpose: str) -> dict:
    """
    Verify submitted_code against the stored OTP for (email, purpose).

    Returns a dict with:
        - success (bool)
        - error (str or None)
        - code (str or None) — error code for frontend handling
    """
    import hmac as _hmac
    from .models import OTP
    email = normalize_email(email)

    try:
        otp = OTP.objects.get(email=email, purpose=purpose)
    except OTP.DoesNotExist:
        return {
            "success": False,
            "error": "No verification code found. Please request a new one.",
            "code": "OTP_NOT_FOUND",
        }

    if otp.is_expired:
        otp.delete()
        return {
            "success": False,
            "error": "Your verification code has expired. Please request a new one.",
            "code": "OTP_EXPIRED",
        }

    if otp.is_blocked:
        return {
            "success": False,
            "error": "Too many failed attempts. Please request a new verification code.",
            "code": "OTP_BLOCKED",
        }

    if not _hmac.compare_digest(str(submitted_code), str(otp.code)):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        max_attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 3)
        remaining = max_attempts - otp.attempts
        return {
            "success": False,
            "error": f"Invalid verification code. {remaining} attempt(s) remaining.",
            "code": "OTP_INVALID",
        }

    otp.delete()
    return {"success": True, "error": None, "code": None}
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python manage.py test accounts.tests.OTPUtilsTests -v 2
```

Expected: `OK` — 4 tests pass.

- [ ] **Step 5: Run full accounts test suite — no regressions**

```bash
python manage.py test accounts -v 2
```

Expected: All existing tests still pass (they don't call `create_and_store_otp` directly yet — callers are updated in Task 4).

- [ ] **Step 6: Commit**

```bash
git add accounts/utils.py
git commit -m "fix(accounts): purpose-scoped OTP, send throttle, constant-time compare (AUTH-01/AUTH-03)"
```

---

## Task 4: Update all OTP callers in views.py (AUTH-01 — wire-up)

**Files:**
- Modify: `accounts/views.py` at lines 90, 130, 337, 541, 551, 628, 645

**Interfaces:**
- Consumes: `create_and_store_otp(email, purpose)` and `verify_otp(email, code, purpose)` from Task 3; `OTP.PURPOSE_*` constants from Task 2

- [ ] **Step 1: Write the failing cross-purpose test**

In `accounts/tests.py`, add:

```python
class OTPCrossPurposeTests(TestCase):
    """A code issued for registration must not satisfy password-reset."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_registration_otp_cannot_satisfy_password_reset(self):
        from accounts.models import OTP
        from accounts.utils import create_and_store_otp, verify_otp
        code = create_and_store_otp("cross@example.com", OTP.PURPOSE_REGISTRATION)
        result = verify_otp("cross@example.com", code, OTP.PURPOSE_PASSWORD_RESET)
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "OTP_NOT_FOUND")

    def test_password_reset_otp_cannot_satisfy_registration(self):
        from accounts.models import OTP
        from accounts.utils import create_and_store_otp, verify_otp
        code = create_and_store_otp("cross2@example.com", OTP.PURPOSE_PASSWORD_RESET)
        result = verify_otp("cross2@example.com", code, OTP.PURPOSE_REGISTRATION)
        self.assertFalse(result["success"])
        self.assertEqual(result["code"], "OTP_NOT_FOUND")
```

- [ ] **Step 2: Run — these should already pass (logic is in utils)**

```bash
python manage.py test accounts.tests.OTPCrossPurposeTests -v 2
```

Expected: `OK` — 2 tests pass (utils already enforce this).

- [ ] **Step 3: Update all 7 OTP call sites in views.py**

Open `accounts/views.py`. Apply these changes one by one:

**Line 90 — RegisterView (create):**
```python
# Before:
otp_code = create_and_store_otp(email)
# After:
from .models import OTP as _OTP
otp_code = create_and_store_otp(email, _OTP.PURPOSE_REGISTRATION)
```

**Line 130 — VerifyOTPView (verify):**
```python
# Before:
result = verify_otp(email, submitted_otp)
# After:
from .models import OTP as _OTP
result = verify_otp(email, submitted_otp, _OTP.PURPOSE_REGISTRATION)
```

**Line 337 — ResendOTPView (create):**
```python
# Before:
otp_code = create_and_store_otp(email)
# After:
from .models import OTP as _OTP
otp_code = create_and_store_otp(email, _OTP.PURPOSE_REGISTRATION)
```

**Line 541 — update_profile email_request (create):**
```python
# Before:
otp_code = create_and_store_otp(new_email)
# After:
from .models import OTP as _OTP
otp_code = create_and_store_otp(new_email, _OTP.PURPOSE_EMAIL_CHANGE)
```

**Line 551 — update_profile email_verify (verify):**
```python
# Before:
result = verify_otp(new_email, otp)
# After:
from .models import OTP as _OTP
result = verify_otp(new_email, otp, _OTP.PURPOSE_EMAIL_CHANGE)
```

**Line 628 — forgot_password (create):**
```python
# Before:
otp_code = create_and_store_otp(email)
# After:
from .models import OTP as _OTP
otp_code = create_and_store_otp(email, _OTP.PURPOSE_PASSWORD_RESET)
```

**Line 645 — forgot_password_verify (verify):**
```python
# Before:
result = verify_otp(email, code)
# After:
from .models import OTP as _OTP
result = verify_otp(email, code, _OTP.PURPOSE_PASSWORD_RESET)
```

**Important:** Move the `from .models import OTP as _OTP` imports to the top of the file with other imports, removing duplication. Find the existing import block at lines 44-48:

```python
from .utils import (
    create_and_store_otp,
    ...
    verify_otp,
)
```

Add `OTP` to the models import at the top of the file (it's likely already imported or near other model imports). Add:

```python
from .models import OTP
```

Then use `OTP.PURPOSE_REGISTRATION` etc. directly — remove all inline `from .models import OTP as _OTP` you added per-site.

- [ ] **Step 4: Handle throttle ValueError in RegisterView and ResendOTPView**

The views call `create_and_store_otp` but now it can raise `ValueError` when throttled. Wrap those calls:

In `RegisterView.post` (around line 90):
```python
try:
    otp_code = create_and_store_otp(email, OTP.PURPOSE_REGISTRATION)
except ValueError:
    return Response(
        {"error": "Too many verification codes requested. Please try again in an hour.", "code": "OTP_THROTTLED"},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
email_sent = send_otp_email(email, otp_code)
```

In `ResendOTPView.post` (around line 337):
```python
try:
    otp_code = create_and_store_otp(email, OTP.PURPOSE_REGISTRATION)
except ValueError:
    return Response(
        {"error": "Too many codes requested. Please try again in an hour.", "code": "OTP_THROTTLED"},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
send_otp_email(email, otp_code)
```

In `forgot_password` (around line 628) — this is a form view returning HTML, so:
```python
try:
    otp_code = create_and_store_otp(email, OTP.PURPOSE_PASSWORD_RESET)
    send_otp_email(email, otp_code)
except ValueError:
    pass  # Silently drop — we already show generic success to prevent enumeration
```

In `update_profile email_request` (around line 541):
```python
try:
    otp_code = create_and_store_otp(new_email, OTP.PURPOSE_EMAIL_CHANGE)
except ValueError:
    return JsonResponse({"error": "Too many codes requested. Try again in an hour."}, status=429)
send_otp_email(new_email, otp_code)
```

- [ ] **Step 5: Run full accounts test suite**

```bash
python manage.py test accounts -v 2
```

Expected: All tests pass, no `TypeError` from missing `purpose` argument.

- [ ] **Step 6: Commit**

```bash
git add accounts/views.py
git commit -m "fix(accounts): wire OTP purpose to all call sites; handle throttle 429 (AUTH-01/AUTH-03)"
```

---

## Task 5: Google OAuth — Block merge on unverified email (AUTH-02)

**Files:**
- Modify: `accounts/adapter.py:7-34`
- Test: `accounts/tests.py`

**Interfaces:**
- Consumes: `allauth.exceptions.ImmediateHttpResponse`, `django.http.HttpResponse`
- Produces: `pre_social_login` raises `ImmediateHttpResponse(400)` when `email_verified` is falsy

- [ ] **Step 1: Write the failing test**

In `accounts/tests.py`, add:

```python
class GoogleOAuthEmailVerifiedTests(TestCase):
    def _make_sociallogin(self, email, email_verified):
        """Build a minimal fake sociallogin object."""
        from unittest.mock import MagicMock
        sl = MagicMock()
        sl.is_existing = False
        sl.account.extra_data = {"email": email, "email_verified": email_verified}
        return sl

    def test_unverified_email_raises_immediate_response(self):
        from allauth.exceptions import ImmediateHttpResponse
        from accounts.adapter import CustomSocialAccountAdapter
        adapter = CustomSocialAccountAdapter()
        sl = self._make_sociallogin("victim@example.com", email_verified=False)
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.pre_social_login(None, sl)
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_verified_email_does_not_raise(self):
        from accounts.adapter import CustomSocialAccountAdapter
        adapter = CustomSocialAccountAdapter()
        sl = self._make_sociallogin("new@example.com", email_verified=True)
        # No existing user → User.DoesNotExist → returns None, no exception
        try:
            adapter.pre_social_login(None, sl)
        except Exception as e:
            self.fail(f"pre_social_login raised unexpectedly: {e}")

    def test_missing_email_verified_key_blocks_merge(self):
        """Absent email_verified key defaults to False — must block."""
        from allauth.exceptions import ImmediateHttpResponse
        from accounts.adapter import CustomSocialAccountAdapter
        adapter = CustomSocialAccountAdapter()
        sl = self._make_sociallogin("no-key@example.com", email_verified=False)
        del sl.account.extra_data["email_verified"]  # simulate absent key
        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(None, sl)
```

- [ ] **Step 2: Run — expect failure**

```bash
python manage.py test accounts.tests.GoogleOAuthEmailVerifiedTests -v 2
```

Expected: FAIL — `AssertionError: ImmediateHttpResponse not raised`

- [ ] **Step 3: Update adapter.py**

Replace `accounts/adapter.py` entirely with:

```python
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.http import HttpResponse

User = get_user_model()


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Merge Google login with existing local account only when the Google
        account's email is verified. Blocks login entirely if not verified.
        """
        if sociallogin.is_existing:
            return

        if "email" not in sociallogin.account.extra_data:
            return

        if not sociallogin.account.extra_data.get("email_verified", False):
            raise ImmediateHttpResponse(
                HttpResponse(
                    "Your Google account email is not verified. "
                    "Please verify your email with Google before signing in.",
                    status=400,
                    content_type="text/plain",
                )
            )

        email = sociallogin.account.extra_data["email"].lower()
        try:
            user = User.objects.get(email=email)
            sociallogin.connect(request, user)
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])
        except User.DoesNotExist:
            pass
```

- [ ] **Step 4: Run tests — expect pass**

```bash
python manage.py test accounts.tests.GoogleOAuthEmailVerifiedTests -v 2
```

Expected: `OK` — 3 tests pass.

- [ ] **Step 5: Run full accounts suite**

```bash
python manage.py test accounts -v 2
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add accounts/adapter.py
git commit -m "fix(accounts): block Google OAuth merge when email_verified is false (AUTH-02)"
```

---

## Task 6: Admin Authorization — Role filter + fin_level allowlist (ADM-01, ADM-02)

**Files:**
- Modify: `superadmin/views.py:152-270`
- Test: `superadmin/tests.py`

**Interfaces:**
- Produces: `employee_update(user_id)` and `employee_delete(user_id)` return 404 for any non-employee user; `employee_create` and `update_fin` return 400 for invalid `fin_level`

- [ ] **Step 1: Write the failing tests**

In `superadmin/tests.py`, add a new test class. Look at the existing test structure to find the `make_user` helper and client login pattern, then add:

```python
class EmployeeManagementAuthzTests(TestCase):
    def setUp(self):
        from accounts.tests import make_user
        self.super_admin = make_user("admin@example.com", role="super_admin")
        self.super_admin.is_staff = True
        self.super_admin.save()
        self.client.force_login(self.super_admin)

    def _post_json(self, url, data):
        import json
        return self.client.post(
            url, data=json.dumps(data), content_type="application/json"
        )

    def test_employee_update_rejects_superadmin_target(self):
        """ADM-01: updating a super_admin UUID must return 404."""
        from django.urls import reverse
        url = reverse("superadmin:employee_update", args=[str(self.super_admin.pk)])
        resp = self._post_json(url, {"action": "lock"})
        # 400 is the self-lock guard; 404 means the role filter fired
        self.assertEqual(resp.status_code, 404)

    def test_employee_update_rejects_guest_target(self):
        """ADM-01: guest user UUID must return 404 from employee endpoint."""
        from accounts.tests import make_user
        from django.urls import reverse
        guest = make_user("guest@example.com", role="guest")
        url = reverse("superadmin:employee_update", args=[str(guest.pk)])
        resp = self._post_json(url, {"action": "lock"})
        self.assertEqual(resp.status_code, 404)

    def test_employee_update_accepts_employee_target(self):
        """ADM-01: a real employee UUID must NOT return 404."""
        from accounts.tests import make_user
        from django.urls import reverse
        emp = make_user("emp@example.com", role="employee")
        url = reverse("superadmin:employee_update", args=[str(emp.pk)])
        resp = self._post_json(url, {"action": "unlock"})
        self.assertNotEqual(resp.status_code, 404)

    def test_employee_create_rejects_invalid_fin_level(self):
        """ADM-02: fin_level outside A/B/C must return 400."""
        resp = self.client.post(
            "/super-admin/employees/create/",
            {
                "email": "new@example.com",
                "full_name": "New Emp",
                "fin_level": "X",
                "properties": [],
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_employee_create_accepts_valid_fin_level(self):
        """ADM-02: fin_level=B must not return 400."""
        resp = self.client.post(
            "/super-admin/employees/create/",
            {
                "email": "valid@example.com",
                "full_name": "Valid Emp",
                "fin_level": "B",
                "properties": [],
            },
        )
        self.assertNotEqual(resp.status_code, 400)
```

- [ ] **Step 2: Run — expect failures**

```bash
python manage.py test superadmin.tests.EmployeeManagementAuthzTests -v 2
```

Expected: FAIL — `employee_update` returns 400 (self-lock) or 200 instead of 404 for non-employee targets; `employee_create` returns 200 instead of 400 for `fin_level=X`.

- [ ] **Step 3: Add role filter to employee_update (ADM-01)**

In `superadmin/views.py`, line 198, change:

```python
# Before:
employee = get_object_or_404(User, pk=user_id)

# After:
employee = get_object_or_404(User, pk=user_id, userprofile__role="employee")
```

- [ ] **Step 4: Add role filter to employee_delete (ADM-01)**

In `superadmin/views.py`, line 260, change:

```python
# Before:
employee = get_object_or_404(User, pk=user_id)

# After:
employee = get_object_or_404(User, pk=user_id, userprofile__role="employee")
```

- [ ] **Step 5: Add fin_level allowlist to employee_create (ADM-02)**

In `superadmin/views.py`, in `employee_create` (starting line 152), add the allowlist check right after the existing `errors` block (after line 167, before `temp_password = ...`):

```python
_FIN_LEVEL_CHOICES = frozenset({"A", "B", "C"})

if fin_level not in _FIN_LEVEL_CHOICES:
    return JsonResponse({"error": "Invalid financial level. Must be A, B, or C."}, status=400)
```

Place `_FIN_LEVEL_CHOICES` as a module-level constant at the top of the employee management section (near line 150), not inside the function, so `update_fin` can also use it.

- [ ] **Step 6: Add fin_level allowlist to update_fin action (ADM-02)**

In `superadmin/views.py`, inside `employee_update`, the `update_fin` branch (around line 237):

```python
if action == "update_fin":
    fin = data.get("fin_level", "C")
    if fin not in _FIN_LEVEL_CHOICES:
        return JsonResponse({"error": "Invalid financial level. Must be A, B, or C."}, status=400)
    employee.userprofile.fin_level = fin
    employee.userprofile.save(update_fields=["fin_level"])
    _log(request, "EMPLOYEE_UPDATED", target_user=employee, detail=f"fin_level→{fin}")
    return JsonResponse({"message": "Financial level updated."})
```

- [ ] **Step 7: Add property ID validation to employee_create and update_properties (ADM-02)**

In `employee_create`, replace lines 183-184:

```python
# Before:
if property_ids:
    profile.assigned_properties.set(Property.objects.filter(id__in=property_ids))

# After:
if property_ids:
    valid_props = Property.objects.filter(id__in=property_ids)
    if valid_props.count() != len(property_ids):
        return JsonResponse({"error": "One or more property IDs are invalid."}, status=400)
    profile.assigned_properties.set(valid_props)
```

In `employee_update` `update_properties` branch (lines 244-250):

```python
if action == "update_properties":
    prop_ids = data.get("property_ids", [])
    valid_props = Property.objects.filter(id__in=prop_ids)
    if valid_props.count() != len(prop_ids):
        return JsonResponse({"error": "One or more property IDs are invalid."}, status=400)
    employee.userprofile.assigned_properties.set(valid_props)
    _log(request, "EMPLOYEE_UPDATED", target_user=employee, detail=f"properties={prop_ids}")
    return JsonResponse({"message": "Properties updated."})
```

- [ ] **Step 8: Run tests — expect pass**

```bash
python manage.py test superadmin.tests.EmployeeManagementAuthzTests -v 2
```

Expected: `OK` — 5 tests pass.

- [ ] **Step 9: Run full superadmin suite**

```bash
python manage.py test superadmin -v 2
```

Expected: All pass.

- [ ] **Step 10: Run entire project test suite**

```bash
python manage.py test accounts rooms payments superadmin employeeadmin loyalty -v 1
```

Expected: All pass — no regressions from any task.

- [ ] **Step 11: Commit**

```bash
git add superadmin/views.py superadmin/tests.py
git commit -m "fix(superadmin): scope employee endpoints to role=employee; allowlist fin_level (ADM-01/ADM-02)"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task that implements it |
|---|---|
| SET-01: Remove hardcoded DB creds | Task 1, Step 1 |
| SET-02: Fail-closed on insecure SECRET_KEY | Task 1, Steps 2-3 |
| AUTH-01: OTP purpose column | Task 2 |
| AUTH-01: create_and_store_otp(email, purpose) | Task 3, Step 3 |
| AUTH-01: verify_otp(email, code, purpose) | Task 3, Step 3 |
| AUTH-01: All 7 callers updated | Task 4, Step 3 |
| AUTH-03: Constant-time compare | Task 3, Step 3 (hmac.compare_digest) |
| AUTH-03: Send throttle 5/hour | Task 3, Step 3 (_check_otp_send_throttle) |
| AUTH-03: 429 on throttle in views | Task 4, Step 4 |
| AUTH-02: Block OAuth merge on unverified email | Task 5, Step 3 |
| ADM-01: role=employee filter on employee_update | Task 6, Step 3 |
| ADM-01: role=employee filter on employee_delete | Task 6, Step 4 |
| ADM-02: fin_level allowlist on create | Task 6, Step 5 |
| ADM-02: fin_level allowlist on update_fin | Task 6, Step 6 |
| ADM-02: property ID validation | Task 6, Step 7 |

All 7 findings fully covered. No placeholders. All code blocks are complete and runnable.
