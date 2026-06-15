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

    def test_superuser_without_profile_role_redirects_to_super_admin_dashboard(self):
        User.objects.create_superuser(
            email="superuser-no-profile@example.com",
            full_name="Super User",
            password="Pass1234!",
        )

        response = self.post_login("superuser-no-profile@example.com")

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


class StaffStayInPortalTests(TestCase):
    """Staff accounts are operational-only: they must not act as guests on the
    customer-facing site. Any staff hit on a customer page bounces to their portal."""

    def test_super_admin_on_home_redirects_to_super_admin_dashboard(self):
        user = make_user("sa-home@example.com", role="super_admin")
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertRedirects(response, "/super-admin/dashboard/", fetch_redirect_response=False)

    def test_employee_admin_on_home_redirects_to_employee_dashboard(self):
        user = make_user("ea-home@example.com", role="employee_admin")
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertRedirects(response, "/admin-portal/dashboard/", fetch_redirect_response=False)

    def test_employee_on_booking_page_redirects_to_employee_dashboard(self):
        user = make_user("emp-book@example.com", role="employee")
        self.client.force_login(user)

        response = self.client.get("/bookings/my-bookings/page/")

        self.assertRedirects(response, "/admin-portal/dashboard/", fetch_redirect_response=False)

    def test_super_admin_on_rooms_search_redirects_to_dashboard(self):
        user = make_user("sa-rooms@example.com", role="super_admin")
        self.client.force_login(user)

        response = self.client.get("/rooms/search/page/")

        self.assertRedirects(response, "/super-admin/dashboard/", fetch_redirect_response=False)

    def test_guest_on_home_is_not_redirected(self):
        user = make_user("guest-home@example.com", role="guest")
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_anonymous_on_home_is_not_redirected(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_super_admin_can_still_reach_their_dashboard(self):
        user = make_user("sa-dash@example.com", role="super_admin")
        self.client.force_login(user)

        response = self.client.get("/super-admin/dashboard/")

        self.assertEqual(response.status_code, 200)

    def test_staff_next_url_into_customer_page_is_not_honored(self):
        make_user("sa-next@example.com", role="super_admin")
        response = self.client.post(
            reverse("accounts:login"),
            data=json.dumps({"email": "sa-next@example.com", "password": "Pass1234!", "next": "/"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/super-admin/dashboard/")


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


class FolioPageTests(TestCase):
    """My Stays (folio) shows only confirmed/completed stays — never abandoned attempts."""

    def _booking(self, user, room, status, days_ahead=5):
        from datetime import timedelta
        from decimal import Decimal
        ci = timezone.now().date() + timedelta(days=days_ahead)
        from rooms.models import Booking
        return Booking.objects.create(
            room=room, user=user, check_in=ci, check_out=ci + timedelta(days=2),
            guests=1, total_price=Decimal('4000'), status=status,
        )

    def setUp(self):
        from decimal import Decimal
        from rooms.models import Property, Room
        self.user = make_user("folio@example.com", role="guest")
        self.client.force_login(self.user)
        prop = Property.objects.create(name='P', city='Pondy', address='x', is_active=True)
        self.room = Room.objects.create(
            property=prop, name='Heritage Suite', city='Pondy', room_type='deluxe',
            price_per_night=Decimal('2000'), capacity=2,
        )

    def test_only_confirmed_and_completed_appear(self):
        self._booking(self.user, self.room, 'confirmed', days_ahead=5)
        self._booking(self.user, self.room, 'pending', days_ahead=20)
        self._booking(self.user, self.room, 'expired', days_ahead=30)
        self._booking(self.user, self.room, 'failed', days_ahead=40)
        res = self.client.get(reverse('accounts:folio'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['stays_count'], 1)
        for s in res.context['stays']:
            self.assertIn(s.status, ('confirmed', 'completed'))

    def test_total_nights_only_counts_stays(self):
        self._booking(self.user, self.room, 'confirmed', days_ahead=5)   # 2 nights
        self._booking(self.user, self.room, 'pending', days_ahead=20)    # ignored
        res = self.client.get(reverse('accounts:folio'))
        self.assertEqual(res.context['nights_stayed'], 2)

    def test_change_password_link_present(self):
        res = self.client.get(reverse('accounts:folio'))
        self.assertContains(res, reverse('accounts:change-password'))
