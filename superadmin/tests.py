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


def _make_employee(email='emp@test.com', created_by=None, last_login=None):
    """Create an employee user + profile. Optionally stamp last_login."""
    user = User.objects.create_user(
        email=email, full_name='Test Employee', phone='8888888888',
        password='emppass123', is_active=True,
    )
    profile = UserProfile.objects.create(user=user, role='employee', fin_level='C')
    if created_by is not None:
        profile.created_by = created_by
        profile.save(update_fields=['created_by'])
    if last_login is not None:
        user.last_login = last_login
        user.save(update_fields=['last_login'])
    return user, profile


class EmployeeManagementTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin, _ = _make_super_admin('sa-emp@test.com')
        self.client.force_login(self.admin)

    # ── URL resolution (the UUID/int root bug) ──────────────────────────────
    def test_employee_update_route_resolves_for_uuid_pk(self):
        emp, _ = _make_employee()
        url = reverse('superadmin:employee-update', args=[emp.pk])
        res = self.client.post(
            url, data=json.dumps({'action': 'lock'}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        emp.refresh_from_db()
        self.assertFalse(emp.is_active)

    def test_unlock_action(self):
        emp, _ = _make_employee('emp2@test.com')
        emp.is_active = False
        emp.save(update_fields=['is_active'])
        url = reverse('superadmin:employee-update', args=[emp.pk])
        res = self.client.post(url, data=json.dumps({'action': 'unlock'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        emp.refresh_from_db()
        self.assertTrue(emp.is_active)

    def test_reset_password_returns_temp(self):
        emp, _ = _make_employee('emp3@test.com')
        url = reverse('superadmin:employee-update', args=[emp.pk])
        res = self.client.post(url, data=json.dumps({'action': 'reset_password'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('temp_password', res.json())

    # ── Revoke ──────────────────────────────────────────────────────────────
    def test_revoke_strips_access_and_stamps(self):
        from rooms.models import Property
        prop = Property.objects.create(name='P', city='Chennai', address='x', is_active=True)
        emp, profile = _make_employee('emp4@test.com')
        profile.assigned_properties.add(prop)
        url = reverse('superadmin:employee-update', args=[emp.pk])
        res = self.client.post(url, data=json.dumps({'action': 'revoke'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        emp.refresh_from_db()
        profile.refresh_from_db()
        self.assertFalse(emp.is_active)
        self.assertIsNotNone(profile.revoked_at)
        self.assertEqual(profile.assigned_properties.count(), 0)
        self.assertEqual(profile.role, 'employee')  # still listed

    def test_revoked_employee_still_appears_in_list(self):
        emp, profile = _make_employee('emp5@test.com')
        profile.revoke(self.admin)
        res = self.client.get(reverse('superadmin:employees'))
        self.assertContains(res, 'emp5@test.com')

    # ── Hard delete ─────────────────────────────────────────────────────────
    def test_hard_delete_allowed_when_never_logged_in(self):
        emp, _ = _make_employee('emp6@test.com')  # last_login None
        url = reverse('superadmin:employee-delete', args=[emp.pk])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(pk=emp.pk).exists())

    def test_hard_delete_blocked_when_logged_in(self):
        emp, _ = _make_employee('emp7@test.com', last_login=timezone.now())
        url = reverse('superadmin:employee-delete', args=[emp.pk])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 400)
        self.assertTrue(User.objects.filter(pk=emp.pk).exists())

    # ── Self-protection ───────────────────────────────────────────────────────
    def test_cannot_revoke_self(self):
        url = reverse('superadmin:employee-update', args=[self.admin.pk])
        res = self.client.post(url, data=json.dumps({'action': 'revoke'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_cannot_delete_self(self):
        url = reverse('superadmin:employee-delete', args=[self.admin.pk])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    # ── Tracking fields ───────────────────────────────────────────────────────
    def test_create_records_created_by(self):
        from rooms.models import Property
        prop = Property.objects.create(name='P2', city='Chennai', address='y', is_active=True)
        res = self.client.post(reverse('superadmin:employee-create'), {
            'email': 'newemp@test.com', 'full_name': 'New Emp',
            'fin_level': 'B', 'properties': [str(prop.id)],
        })
        self.assertEqual(res.status_code, 200)
        new = User.objects.get(email='newemp@test.com')
        self.assertEqual(new.userprofile.created_by, self.admin)

    def test_list_renders_tracking_columns(self):
        _make_employee('emp8@test.com', created_by=self.admin)
        res = self.client.get(reverse('superadmin:employees'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'emp8@test.com')


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
