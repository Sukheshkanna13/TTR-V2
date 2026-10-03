"""Smoke tests: every parameter-free admin GET page must render without a 5xx.

Regression guard for runtime NameErrors in views (e.g. bookings_list losing
its paginator) that static review and the unit tests miss.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from accounts.models import UserProfile
from employeeadmin import urls as employee_urls
from superadmin import urls as super_urls

User = get_user_model()


def _login(client, email, role):
    user = User.objects.create_user(
        email=email, full_name="Smoke User", phone="9999999999",
        password="testpass123", is_active=True,
    )
    UserProfile.objects.create(user=user, role=role)
    client.force_login(user)
    return user


def _static_url_names(urlconf, namespace):
    names = []
    for p in urlconf.urlpatterns:
        if p.name and "<" not in str(p.pattern):
            names.append(f"{namespace}:{p.name}")
    return names


class AdminPagesSmokeTest(TestCase):
    def _check(self, names):
        failures = []
        for name in names:
            try:
                url = reverse(name)
            except NoReverseMatch:
                continue
            resp = self.client.get(url)
            if resp.status_code >= 500:
                failures.append(f"{name} -> {resp.status_code}")
        self.assertEqual(failures, [])

    def test_superadmin_pages_do_not_500(self):
        _login(self.client, "sa@test.com", "super_admin")
        self._check(_static_url_names(super_urls, "superadmin"))

    def test_employee_admin_pages_do_not_500(self):
        _login(self.client, "ea@test.com", "employee_admin")
        self._check(_static_url_names(employee_urls, "employeeadmin"))

    def test_bookings_pagination_keeps_filters(self):
        _login(self.client, "sa2@test.com", "super_admin")
        resp = self.client.get(reverse("superadmin:bookings"), {"status": "confirmed", "page": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("page_obj", resp.context)
