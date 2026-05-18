import json
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import LoginAttempt, UserProfile


User = get_user_model()


def make_user(email, role="guest", password="Pass1234!", **profile_fields):
    user = User.objects.create_user(
        email=email,
        full_name="Test User",
        phone="9999999999",
        password=password,
        is_active=True,
    )
    UserProfile.objects.create(user=user, role=role, **profile_fields)
    return user


class UnifiedLoginRedirectTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:login")

    def post_login(self, email, password="Pass1234!", next_url=None):
        payload = {"email": email, "password": password}
        if next_url is not None:
            payload["next"] = next_url
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_guest_login_returns_home_redirect(self):
        make_user("guest@example.com", role="guest")

        response = self.post_login("guest@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/")

    def test_employee_login_returns_dashboard_redirect(self):
        make_user("employee@example.com", role="employee")

        response = self.post_login("employee@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/admin-portal/dashboard/")

    def test_employee_admin_login_returns_employee_dashboard_redirect(self):
        make_user("employee-admin@example.com", role="employee_admin")

        response = self.post_login("employee-admin@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/admin-portal/dashboard/")

    def test_super_admin_login_returns_super_admin_dashboard_redirect(self):
        make_user("super-admin@example.com", role="super_admin")

        response = self.post_login("super-admin@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/super-admin/dashboard/")

    def test_admin_must_change_password_goes_straight_to_dashboard(self):
        make_user("admin-reset@example.com", role="employee_admin", must_change_password=True)

        response = self.post_login("admin-reset@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/admin-portal/dashboard/")

    def test_guest_cannot_use_next_to_enter_super_admin_area(self):
        make_user("guest-next@example.com", role="guest")

        response = self.post_login("guest-next@example.com", next_url="/super-admin/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/")

    def test_employee_admin_can_use_next_inside_employee_portal(self):
        make_user("admin-next@example.com", role="employee_admin")

        response = self.post_login("admin-next@example.com", next_url="/admin-portal/rooms/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/admin-portal/rooms/")

    def test_external_next_url_is_ignored(self):
        make_user("external-next@example.com", role="guest")

        response = self.post_login("external-next@example.com", next_url="https://evil.example/login")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/")

    def test_locked_account_returns_structured_response(self):
        make_user("locked@example.com", role="guest")
        LoginAttempt.objects.create(
            email="locked@example.com",
            attempts=5,
            locked_until=timezone.now() + timezone.timedelta(minutes=4),
        )

        response = self.post_login("locked@example.com")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["code"], "ACCOUNT_LOCKED")
        self.assertGreaterEqual(response.json()["remaining_minutes"], 1)

    def test_successful_login_clears_failed_attempts_for_normalized_email(self):
        make_user("normalize@example.com", role="guest")
        LoginAttempt.objects.create(email="normalize@example.com", attempts=2)

        response = self.post_login(" NORMALIZE@example.com ")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(LoginAttempt.objects.filter(email="normalize@example.com").exists())


class PortalAccessTests(TestCase):
    def test_anonymous_super_admin_page_redirects_to_central_login(self):
        response = self.client.get("/super-admin/dashboard/")

        self.assertRedirects(
            response,
            "/accounts/login/page/?next=%2Fsuper-admin%2Fdashboard%2F",
            fetch_redirect_response=False,
        )

    def test_anonymous_employee_admin_page_redirects_to_central_login(self):
        response = self.client.get("/admin-portal/dashboard/")

        self.assertRedirects(
            response,
            "/accounts/login/page/?next=%2Fadmin-portal%2Fdashboard%2F",
            fetch_redirect_response=False,
        )

    def test_employee_admin_cannot_access_super_admin_dashboard(self):
        user = make_user("portal-admin@example.com", role="employee_admin")
        self.client.force_login(user)

        response = self.client.get("/super-admin/dashboard/")

        self.assertRedirects(response, "/accounts/login/page/", fetch_redirect_response=False)

    def test_employee_can_access_employee_admin_dashboard(self):
        user = make_user("plain-employee@example.com", role="employee")
        self.client.force_login(user)

        response = self.client.get("/admin-portal/dashboard/")

        self.assertEqual(response.status_code, 200)

    def test_old_admin_portal_login_redirects_to_central_login(self):
        response = self.client.get("/admin-portal/login/")

        self.assertRedirects(response, "/accounts/login/page/?next=%2Fadmin-portal%2Flogin%2F", fetch_redirect_response=False)

    def test_old_super_admin_login_redirects_to_central_login(self):
        response = self.client.get("/super-admin/login/")

        self.assertRedirects(response, "/accounts/login/page/?next=%2Fsuper-admin%2Flogin%2F", fetch_redirect_response=False)


class LoginRecoveryCommandTests(TestCase):
    def test_clear_login_locks_removes_specific_email_only(self):
        LoginAttempt.objects.create(email="one@example.com", attempts=5)
        LoginAttempt.objects.create(email="two@example.com", attempts=5)

        out = StringIO()
        call_command("clear_login_locks", email="one@example.com", stdout=out)

        self.assertIn("Cleared 1 login lock", out.getvalue())
        self.assertFalse(LoginAttempt.objects.filter(email="one@example.com").exists())
        self.assertTrue(LoginAttempt.objects.filter(email="two@example.com").exists())

    def test_clear_login_locks_can_clear_cache(self):
        cache.set("login-test-key", "present", timeout=60)

        call_command("clear_login_locks", clear_cache=True, stdout=StringIO())

        self.assertIsNone(cache.get("login-test-key"))

    def test_bootstrap_superadmin_repairs_user_profile_and_clears_lock(self):
        make_user("boss@example.com", role="guest")
        LoginAttempt.objects.create(email="boss@example.com", attempts=5)

        out = StringIO()
        call_command(
            "bootstrap_superadmin",
            email="boss@example.com",
            password="BossPass123!",
            stdout=out,
        )

        user = User.objects.get(email="boss@example.com")
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("BossPass123!"))
        self.assertEqual(user.userprofile.role, "super_admin")
        self.assertFalse(user.userprofile.must_change_password)
        self.assertFalse(LoginAttempt.objects.filter(email="boss@example.com").exists())
        self.assertIn("Super admin ready", out.getvalue())

    def test_dev_settings_use_testing_friendly_lock_policy(self):
        self.assertEqual(settings.LOGIN_MAX_ATTEMPTS, 20)
        self.assertEqual(settings.LOGIN_LOCK_DURATION_MINUTES, 1)
