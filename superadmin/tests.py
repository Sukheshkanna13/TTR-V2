import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from accounts.models import UserProfile

User = get_user_model()


def _make_super_admin(email='superadmin@test.com', password='testpass123'):
    """Create a super_admin user with a UserProfile and return (user, password)."""
    user = User.objects.create_user(
        email=email,
        full_name='Test Super Admin',
        phone='9999999999',
        password=password,
        is_active=True,
    )
    UserProfile.objects.create(user=user, role='super_admin')
    return user, password


class DashboardLiveDataTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.password = _make_super_admin()
        self.client.force_login(self.user)
        self.url = reverse('superadmin:dashboard-live')

    def test_live_data_returns_json(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content)
        for key in ('active_bookings', 'pending_holds', 'todays_checkins', 'todays_checkouts', 'today_revenue'):
            self.assertIn(key, data, msg=f"Missing key: {key}")

    def test_pending_holds_include_expires_at(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIsInstance(data['pending_holds'], list)
        # Each hold entry must carry an 'expires_at' field (may be None)
        for hold in data['pending_holds']:
            self.assertIn('expires_at', hold, msg="Hold entry missing 'expires_at' field")
