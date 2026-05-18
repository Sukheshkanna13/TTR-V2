import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

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

    def test_today_revenue_only_includes_todays_checkins(self):
        from rooms.models import Property, Room, Booking
        from decimal import Decimal

        prop = Property.objects.create(
            name='Test Prop', city='Chennai', address='1 Main St', is_active=True,
        )
        room = Room.objects.create(
            property=prop, name='R1', city='Chennai', room_type='single',
            price_per_night=Decimal('1500'), capacity=2,
        )
        today = timezone.now().date()
        tomorrow = today + timezone.timedelta(days=1)
        day_after = today + timezone.timedelta(days=2)

        # Booking checking in today
        Booking.objects.create(
            user=self.user, room=room,
            check_in=today, check_out=tomorrow,
            status='confirmed', total_price=Decimal('1500'), guests=1,
        )
        # Booking checking in tomorrow (must NOT be in today_revenue)
        Booking.objects.create(
            user=self.user, room=room,
            check_in=tomorrow, check_out=day_after,
            status='confirmed', total_price=Decimal('2000'), guests=1,
        )

        res = self.client.get(reverse('superadmin:dashboard-live'))
        data = res.json()
        self.assertAlmostEqual(data['today_revenue'], 1500.0, places=0)

    def test_active_bookings_excludes_checkouts_today(self):
        from rooms.models import Property, Room, Booking
        from decimal import Decimal

        prop = Property.objects.create(
            name='Test Prop2', city='Bangalore', address='2 Main St', is_active=True,
        )
        room = Room.objects.create(
            property=prop, name='R2', city='Bangalore', room_type='double',
            price_per_night=Decimal('2000'), capacity=3,
        )
        today = timezone.now().date()
        yesterday = today - timezone.timedelta(days=1)

        # Booking checking out today — must NOT be counted as active
        Booking.objects.create(
            user=self.user, room=room,
            check_in=yesterday, check_out=today,
            status='confirmed', total_price=Decimal('2000'), guests=1,
        )

        res = self.client.get(reverse('superadmin:dashboard-live'))
        data = res.json()
        self.assertEqual(data['active_bookings'], 0)


class RoomStatusBoardTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user, _ = _make_super_admin('sa2@test.com')
        self.client.force_login(self.user)

    def test_status_board_renders(self):
        res = self.client.get(reverse('superadmin:room-status-board'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'status-board')

    def test_status_board_json_returns_rooms(self):
        from rooms.models import Property, Room
        prop = Property.objects.create(
            name='Test Prop', city='Chennai', address='1 Main St', is_active=True,
        )
        Room.objects.create(
            property=prop, name='R1', city='Chennai', room_type='single',
            price_per_night=1000, capacity=2, operational_status='available',
        )
        res = self.client.get(reverse('superadmin:room-status-board-data'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('rooms', data)
        self.assertEqual(len(data['rooms']), 1)
        self.assertEqual(data['rooms'][0]['status'], 'available')
