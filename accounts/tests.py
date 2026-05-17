import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile


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

    def test_employee_login_returns_home_redirect(self):
        make_user("employee@example.com", role="employee")

        response = self.post_login("employee@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/")

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

    def test_must_change_password_redirects_before_dashboard(self):
        make_user("admin-reset@example.com", role="employee_admin", must_change_password=True)

        response = self.post_login("admin-reset@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect_url"], "/accounts/change-password/")

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

    def test_employee_cannot_access_employee_admin_dashboard(self):
        user = make_user("plain-employee@example.com", role="employee")
        self.client.force_login(user)

        response = self.client.get("/admin-portal/dashboard/")

        self.assertRedirects(response, "/accounts/login/page/", fetch_redirect_response=False)

    def test_old_admin_portal_login_redirects_to_central_login(self):
        response = self.client.get("/admin-portal/login/")

        self.assertRedirects(response, "/accounts/login/page/", fetch_redirect_response=False)

    def test_old_super_admin_login_redirects_to_central_login(self):
        response = self.client.get("/super-admin/login/")

        self.assertRedirects(response, "/accounts/login/page/", fetch_redirect_response=False)
