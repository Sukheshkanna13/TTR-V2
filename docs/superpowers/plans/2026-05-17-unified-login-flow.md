# Unified Login Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One login page for all users — after auth, the server reads the user's role and redirects them to the correct destination. No separate staff login pages exist.

**Architecture:** The existing `/accounts/login/page/` + `LoginView` API is the single and only login entry point for every user type. `LoginView.post()` returns a `redirect_url` in its success payload based on `UserProfile.role`. The `login.html` JS reads that URL and navigates. All separate employee/super-admin login views, their URLs, and their templates are deleted. The actual portal business logic (employeeadmin views, superadmin views, decorators, templates) is untouched — only the login infrastructure is removed.

**Tech Stack:** Django 6, DRF, vanilla JS (fetch API), `UserProfile.role` (`guest` | `employee` | `super_admin`)

---

## What Gets Deleted vs What Stays

| Layer | DELETE (login infrastructure) | KEEP (portal logic) |
|-------|-------------------------------|---------------------|
| Views | `employee_login_page()`, `super_admin_login_page()` in `accounts/views.py` | All views in `employeeadmin/views.py`, `superadmin/views.py` |
| URLs | `/admin-portal/login/`, `/super-admin/login/`, `employee-login/`, `super-admin-login/` | All `/admin-portal/*` and `/super-admin/*` routes except the login ones |
| Templates | `employee_login.html`, `super_admin_login.html` | All employeeadmin and superadmin portal templates |
| Decorators | — nothing deleted | Update redirect target only |

---

## Destination URLs (server-authoritative)

| Role | Redirect destination |
|------|---------------------|
| `super_admin` | `/super-admin/dashboard/` |
| `employee` | `/admin-portal/dashboard/` |
| `guest` | `?next=` param if present, else `/` (home) |

---

## File Map

| File | Action | Change |
|------|--------|--------|
| `accounts/views.py` | Modify + delete | Add role→redirect_url to `LoginView.post()`; delete `employee_login_page` and `super_admin_login_page` |
| `hotel_booking/urls.py` | Modify | Remove two login route lines |
| `accounts/urls.py` | Modify | Remove two login route lines |
| `superadmin/decorators.py` | Modify | Redirect target → `/accounts/login/page/` |
| `employeeadmin/decorators.py` | Modify | Redirect target → `/accounts/login/page/` |
| `templates/accounts/login.html` | Modify | JS success branch: use `data.redirect_url` |
| `templates/accounts/employee_login.html` | Delete | Gone |
| `templates/accounts/super_admin_login.html` | Delete | Gone |
| `accounts/tests.py` | Create | Tests for role-based redirect behaviour |

---

## Task 1: Write failing tests

**Files:**
- Create: `accounts/tests.py`

- [ ] **Step 1: Create the test file**

```python
# accounts/tests.py
import json
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User


def _make_user(email, password, role):
    user = User.objects.create_user(email=email, password=password, is_active=True)
    user.userprofile.role = role
    user.userprofile.save()
    return user


class LoginRedirectTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:login')

    def _post(self, email, password):
        return self.client.post(
            self.url,
            data=json.dumps({'email': email, 'password': password}),
            content_type='application/json',
        )

    def test_guest_login_returns_null_redirect_url(self):
        _make_user('guest@example.com', 'pass1234', 'guest')
        res = self._post('guest@example.com', 'pass1234')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json().get('redirect_url'))

    def test_employee_login_returns_employee_dashboard_url(self):
        _make_user('emp@example.com', 'pass1234', 'employee')
        res = self._post('emp@example.com', 'pass1234')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['redirect_url'], '/admin-portal/dashboard/')

    def test_super_admin_login_returns_superadmin_dashboard_url(self):
        _make_user('sa@example.com', 'pass1234', 'super_admin')
        res = self._post('sa@example.com', 'pass1234')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['redirect_url'], '/super-admin/dashboard/')


class DecoratorRedirectTest(TestCase):
    def test_require_super_admin_bounces_anonymous_to_unified_login(self):
        res = self.client.get('/super-admin/dashboard/')
        self.assertRedirects(res, '/accounts/login/page/', fetch_redirect_response=False)

    def test_require_employee_bounces_anonymous_to_unified_login(self):
        res = self.client.get('/admin-portal/dashboard/')
        self.assertRedirects(res, '/accounts/login/page/', fetch_redirect_response=False)
```

- [ ] **Step 2: Run tests — confirm they all FAIL**

```bash
cd /Users/sukheshkannasaravanan/Documents/GitHub/TTR-V2
python manage.py test accounts.tests --settings=hotel_booking.settings.dev -v 2
```

Expected: 5 failures — `redirect_url` key missing in response, decorator redirects still go to old URLs.

---

## Task 2: Add `redirect_url` to `LoginView.post()`

**Files:**
- Modify: `accounts/views.py` — `LoginView.post()` success return

- [ ] **Step 1: Find the success return in `LoginView.post()`**

In `accounts/views.py`, locate `LoginView`. The success return currently looks like:

```python
        reset_login_attempts(email)
        login(request, user, backend="accounts.backends.EmailBackend")
        logger.info("User logged in: %s", email)

        return Response(
            {"message": "Login successful.", "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )
```

- [ ] **Step 2: Replace the success return block with this**

```python
        reset_login_attempts(email)
        login(request, user, backend="accounts.backends.EmailBackend")
        logger.info("User logged in: %s", email)

        role = getattr(getattr(user, 'userprofile', None), 'role', 'guest')
        if role == 'super_admin':
            redirect_url = '/super-admin/dashboard/'
        elif role == 'employee':
            redirect_url = '/admin-portal/dashboard/'
        else:
            redirect_url = None

        return Response(
            {
                "message": "Login successful.",
                "user": UserSerializer(user).data,
                "redirect_url": redirect_url,
            },
            status=status.HTTP_200_OK,
        )
```

- [ ] **Step 3: Run just the `LoginRedirectTest` to verify 3 pass**

```bash
python manage.py test accounts.tests.LoginRedirectTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add accounts/views.py accounts/tests.py
git commit -m "feat: LoginView returns role-based redirect_url in success response"
```

---

## Task 3: Update decorators to bounce to unified login

**Files:**
- Modify: `superadmin/decorators.py`
- Modify: `employeeadmin/decorators.py`

- [ ] **Step 1: Rewrite `superadmin/decorators.py`**

```python
from functools import wraps
from django.shortcuts import redirect


def require_super_admin(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/accounts/login/page/')
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role != 'super_admin':
            return redirect('/accounts/login/page/')
        return view_func(request, *args, **kwargs)
    return wrapper
```

- [ ] **Step 2: Rewrite `employeeadmin/decorators.py`**

```python
from functools import wraps
from django.shortcuts import redirect


def require_employee(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/accounts/login/page/')
        if not hasattr(request.user, 'userprofile') or request.user.userprofile.role not in ('employee', 'super_admin'):
            return redirect('/accounts/login/page/')
        return view_func(request, *args, **kwargs)
    return wrapper
```

- [ ] **Step 3: Run full test suite — all 5 should pass now**

```bash
python manage.py test accounts.tests --settings=hotel_booking.settings.dev -v 2
```

Expected: 5 PASS.

- [ ] **Step 4: Commit**

```bash
git add superadmin/decorators.py employeeadmin/decorators.py
git commit -m "fix: admin decorators redirect to /accounts/login/page/ (unified login)"
```

---

## Task 4: Update `login.html` JS to use `redirect_url`

**Files:**
- Modify: `templates/accounts/login.html`

Current success branch in `handleLogin` (around line 77):
```javascript
      if (res.ok) {
        const data = await res.json();
        if (data.user && data.user.is_staff) {
          window.location.href = '/admin/';
        } else {
          const urlParams = new URLSearchParams(window.location.search);
          const next = urlParams.get('next');
          window.location.href = next && next.startsWith('/') ? next : "{% url 'core:home' %}";
        }
```

- [ ] **Step 1: Replace that block with**

```javascript
      if (res.ok) {
        const data = await res.json();
        if (data.redirect_url) {
          window.location.href = data.redirect_url;
        } else {
          const urlParams = new URLSearchParams(window.location.search);
          const next = urlParams.get('next');
          window.location.href = next && next.startsWith('/') ? next : "{% url 'core:home' %}";
        }
```

Rule: when the server returns a `redirect_url` (employees and super admins), go there unconditionally. Guests get no `redirect_url` so the existing `?next=` / home fallback handles them exactly as before.

- [ ] **Step 2: Commit**

```bash
git add templates/accounts/login.html
git commit -m "fix: login.html JS uses server-driven redirect_url for role routing"
```

---

## Task 5: Remove old login URL routes

**Files:**
- Modify: `hotel_booking/urls.py`
- Modify: `accounts/urls.py`

- [ ] **Step 1: In `hotel_booking/urls.py`, delete these two lines**

```python
path("admin-portal/login/", accounts_views.employee_login_page, name="admin-portal-login"),
path("super-admin/login/", accounts_views.super_admin_login_page, name="super-admin-login"),
```

- [ ] **Step 2: In `accounts/urls.py`, delete these two lines**

```python
path("employee-login/", views.employee_login_page, name="employee-login-page"),
path("super-admin-login/", views.super_admin_login_page, name="super-admin-login-page"),
```

- [ ] **Step 3: Commit**

```bash
git add hotel_booking/urls.py accounts/urls.py
git commit -m "chore: remove old staff login URL routes"
```

---

## Task 6: Delete old login view functions

**Files:**
- Modify: `accounts/views.py` — remove two functions

- [ ] **Step 1: Delete `employee_login_page` function**

In `accounts/views.py`, find and delete the entire `employee_login_page` function. It starts with:
```python
def employee_login_page(request):
    """
    Staff login page for employees.
```
and ends just before `def super_admin_login_page`.

- [ ] **Step 2: Delete `super_admin_login_page` function**

Delete the entire `super_admin_login_page` function. It starts with:
```python
def super_admin_login_page(request):
    """
    Super Admin login page.
```

- [ ] **Step 3: Run system check**

```bash
python manage.py check --settings=hotel_booking.settings.dev
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Run full test suite**

```bash
python manage.py test accounts.tests --settings=hotel_booking.settings.dev -v 2
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add accounts/views.py
git commit -m "chore: delete employee_login_page and super_admin_login_page views"
```

---

## Task 7: Delete old login templates and verify zero stale references

**Files:**
- Delete: `templates/accounts/employee_login.html`
- Delete: `templates/accounts/super_admin_login.html`

- [ ] **Step 1: Delete the two template files**

```bash
rm templates/accounts/employee_login.html
rm templates/accounts/super_admin_login.html
```

- [ ] **Step 2: Grep for any remaining references to the old login routes**

```bash
grep -rn \
  "employee-login\|super-admin-login\|employee_login_page\|super_admin_login_page\|admin-portal/login\|super-admin/login" \
  --include="*.py" --include="*.html" .
```

Expected: zero results. If any appear, delete or update those references before proceeding.

- [ ] **Step 3: Run final system check**

```bash
python manage.py check --settings=hotel_booking.settings.dev
```

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "chore: delete obsolete staff login templates"
```

---

## Final Manual Smoke Test

Start the dev server and test every login scenario:

```bash
python manage.py runserver --settings=hotel_booking.settings.dev
```

| Scenario | Expected result |
|----------|----------------|
| Visit `/accounts/login/page/`, log in as **guest** | → `/` (home) |
| Visit `/accounts/login/page/?next=/accounts/folio/`, log in as **guest** | → `/accounts/folio/` |
| Visit `/accounts/login/page/`, log in as **employee** | → `/admin-portal/dashboard/` |
| Visit `/accounts/login/page/`, log in as **super_admin** | → `/super-admin/dashboard/` |
| Visit `/super-admin/dashboard/` while logged out | → `/accounts/login/page/` |
| Visit `/admin-portal/dashboard/` while logged out | → `/accounts/login/page/` |
| Visit `/admin-portal/login/` (old URL) | 404 |
| Visit `/super-admin/login/` (old URL) | 404 |
| Log in as **guest**, manually visit `/super-admin/dashboard/` | → `/accounts/login/page/` (decorator blocks it) |
