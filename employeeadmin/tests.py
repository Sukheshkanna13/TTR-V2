import datetime

from django.test import TestCase, Client, RequestFactory
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import UserProfile
from rooms.models import Room, Property, Booking
from employeeadmin.views import _assigned_rooms

User = get_user_model()


def make_user(email, phone, role='guest'):
    user = User.objects.create_user(
        email=email, full_name='Test User', phone=phone, password='x', is_active=True,
    )
    UserProfile.objects.create(user=user, role=role)
    return user


class AssignedRoomsSecurityTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.prop_a = Property.objects.create(name='Prop A', city='Pondy', is_active=True)
        self.prop_b = Property.objects.create(name='Prop B', city='Bengaluru', is_active=True)
        Room.objects.create(property=self.prop_a, name='A1', city='Pondy',
                            room_type='single', price_per_night=1000, capacity=2)
        Room.objects.create(property=self.prop_b, name='B1', city='Bengaluru',
                            room_type='single', price_per_night=1000, capacity=2)
        self.user = make_user('emp@example.com', '9000000001', role='employee_admin')

    def _req(self):
        req = self.factory.get('/')
        req.user = self.user
        return req

    def test_employee_with_no_properties_sees_no_rooms(self):
        self.assertEqual(_assigned_rooms(self._req()).count(), 0)

    def test_employee_sees_only_assigned_property_rooms(self):
        self.user.userprofile.assigned_properties.add(self.prop_a)
        rooms = _assigned_rooms(self._req())
        self.assertEqual(rooms.count(), 1)
        self.assertEqual(rooms.first().property_id, self.prop_a.id)

    def test_broken_profile_sees_no_rooms(self):
        broken_user = User.objects.create_user(
            email='x@x.com', full_name='X', phone='9000000002', password='x', is_active=True,
        )
        req = self.factory.get('/')
        req.user = broken_user
        self.assertEqual(_assigned_rooms(req).count(), 0)


class EmployeeScopeTest(TestCase):
    def setUp(self):
        self.prop_a = Property.objects.create(name='Prop A', city='Pondy', is_active=True)
        self.prop_b = Property.objects.create(name='Prop B', city='Bengaluru', is_active=True)
        self.room_a = Room.objects.create(property=self.prop_a, name='A1', city='Pondy',
                                          room_type='single', price_per_night=1000, capacity=2)
        self.room_b = Room.objects.create(property=self.prop_b, name='B1', city='Bengaluru',
                                          room_type='single', price_per_night=1000, capacity=2)

        self.guest = make_user('g@x.com', '9000000003', role='guest')
        today = datetime.date.today()
        Booking.objects.create(room=self.room_a, user=self.guest, check_in=today,
                               check_out=today + datetime.timedelta(days=2),
                               guests=1, status='confirmed', total_price=2000)
        Booking.objects.create(room=self.room_b, user=self.guest, check_in=today,
                               check_out=today + datetime.timedelta(days=2),
                               guests=1, status='confirmed', total_price=2000)

        self.emp = make_user('e@x.com', '9000000004', role='employee_admin')
        self.emp.userprofile.assigned_properties.add(self.prop_a)

    def test_dashboard_only_shows_assigned_property_bookings(self):
        self.client.force_login(self.emp)
        res = self.client.get(reverse('employeeadmin:dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['active_bookings'], 1)

    def test_bookings_list_only_shows_assigned_property_bookings(self):
        self.client.force_login(self.emp)
        res = self.client.get(reverse('employeeadmin:bookings'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.context['bookings']), 1)
        self.assertEqual(res.context['bookings'][0].room.property_id, self.prop_a.id)


class EmployeeDashboardLiveDataTest(TestCase):
    def setUp(self):
        self.emp = make_user('emp@live.test', '8888888888', role='employee_admin')
        self.client = Client()
        self.client.force_login(self.emp)

    def test_live_data_returns_json(self):
        res = self.client.get(reverse('employeeadmin:dashboard-live'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('active_bookings', data)
        self.assertIn('todays_checkins', data)
        self.assertIn('todays_checkouts', data)

    def test_employee_with_no_properties_sees_zero_counts(self):
        res = self.client.get(reverse('employeeadmin:dashboard-live'))
        data = res.json()
        self.assertEqual(data['active_bookings'], 0)
        self.assertEqual(data['todays_checkins'], 0)
        self.assertEqual(data['todays_checkouts'], 0)
