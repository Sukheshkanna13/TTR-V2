"""
Hardening tests for the Employee Admin panel (admin-panels audit 2026-10-18).

Covers: C2 (complete_stay), C4 (financial gating), H1 (audit trail),
H2 (no 500s on bad input), H6 (Channex pushes), H7 (room validation),
M4 (block/rate ranges), walk-in guest validation and the low-severity items.
"""
import json
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from rooms.models import Booking, OTABlock, Room, RoomImage, RoomRate, Property
from superadmin.models import AuditLog

User = get_user_model()

TEST_PASSWORD = 'x'
# Smallest valid GIF, enough for an ImageField upload.
TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00'
    b'\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
)


def make_user(email, phone, role='guest', fin_level=''):
    user = User.objects.create_user(
        email=email, full_name='Test User', phone=phone, password=TEST_PASSWORD, is_active=True,
    )
    UserProfile.objects.create(user=user, role=role, fin_level=fin_level)
    return user


class HardeningBase(TestCase):
    """Two properties, one employee per financial level, all assigned to prop_a."""

    def setUp(self):
        self.prop_a = Property.objects.create(name='Prop A', city='Pondy', is_active=True)
        self.prop_b = Property.objects.create(name='Prop B', city='Bengaluru', is_active=True)
        self.room = Room.objects.create(
            property=self.prop_a, name='A1', city='Pondy',
            room_type='single', price_per_night=1000, capacity=2,
        )
        self.other_room = Room.objects.create(
            property=self.prop_b, name='B1', city='Bengaluru',
            room_type='single', price_per_night=1000, capacity=2,
        )
        self.emp_a = self._employee('ea@hard.test', '9100000001', 'A')
        self.emp_b = self._employee('eb@hard.test', '9100000002', 'B')
        self.emp_c = self._employee('ec@hard.test', '9100000003', 'C')
        self.guest = make_user('guest@hard.test', '9100000009', role='guest')

        self.client_a = self._client(self.emp_a)
        self.client_b = self._client(self.emp_b)
        self.client_c = self._client(self.emp_c)

    def _employee(self, email, phone, fin):
        user = make_user(email, phone, role='employee_admin', fin_level=fin)
        user.userprofile.assigned_properties.add(self.prop_a)
        return user

    @staticmethod
    def _client(user):
        c = Client(raise_request_exception=False)
        c.force_login(user)
        return c

    def post_json(self, client, room, payload):
        return client.post(
            reverse('employeeadmin:room-edit', args=[room.id]),
            data=json.dumps(payload), content_type='application/json',
        )

    def make_booking(self, check_in, check_out, status='confirmed', room=None):
        return Booking.objects.create(
            room=room or self.room, user=self.guest, check_in=check_in, check_out=check_out,
            guests=1, status=status, total_price=1000,
            booking_reference=f'TT-TEST-{Booking.objects.count() + 1:05d}'
            if status == 'confirmed' else None,
        )

    def audit_rows(self, action):
        return AuditLog.objects.filter(action=action)

    def walk_in_payload(self, **overrides):
        today = date.today()
        data = {
            'room_id': str(self.room.id),
            'check_in': (today + timedelta(days=10)).isoformat(),
            'check_out': (today + timedelta(days=12)).isoformat(),
            'guest_name': 'Walk In',
            'guest_phone': '9876500001',
            'guests': '2',
            'payment_method': 'cash',
        }
        data.update(overrides)
        return data


# ── C2: booking_complete uses Booking.complete_stay ─────────────────────────────

class BookingCompleteTests(HardeningBase):
    def url(self, booking):
        return reverse('employeeadmin:booking-complete', args=[booking.id])

    def test_complete_future_booking_is_400_and_unchanged(self):
        today = timezone.localdate()
        b = self.make_booking(today + timedelta(days=3), today + timedelta(days=5))
        res = self.client_a.post(self.url(b))
        self.assertEqual(res.status_code, 400)
        self.assertIn('error', res.json())
        b.refresh_from_db()
        self.assertEqual(b.status, 'confirmed')

    def test_complete_in_progress_stay_shortens_check_out(self):
        today = timezone.localdate()
        b = self.make_booking(today - timedelta(days=1), today + timedelta(days=3))
        res = self.client_a.post(self.url(b))
        self.assertEqual(res.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.status, 'completed')
        self.assertEqual(b.check_out, today)

    def test_complete_after_checkout_date_keeps_dates(self):
        today = timezone.localdate()
        b = self.make_booking(today - timedelta(days=4), today - timedelta(days=1))
        res = self.client_a.post(self.url(b))
        self.assertEqual(res.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.status, 'completed')
        self.assertEqual(b.check_out, today - timedelta(days=1))

    def test_complete_non_confirmed_is_400(self):
        today = timezone.localdate()
        b = self.make_booking(today - timedelta(days=1), today + timedelta(days=1), status='cancelled')
        res = self.client_a.post(self.url(b))
        self.assertEqual(res.status_code, 400)

    def test_complete_writes_audit_row(self):
        today = timezone.localdate()
        b = self.make_booking(today - timedelta(days=1), today + timedelta(days=1))
        self.client_a.post(self.url(b))
        rows = self.audit_rows('BOOKING_COMPLETED')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().actor, self.emp_a)
        self.assertIn(b.booking_reference, rows.first().detail)

    def test_failed_complete_writes_no_audit_row(self):
        today = timezone.localdate()
        b = self.make_booking(today + timedelta(days=3), today + timedelta(days=5))
        self.client_a.post(self.url(b))
        self.assertEqual(self.audit_rows('BOOKING_COMPLETED').count(), 0)

    def test_cannot_complete_unassigned_booking(self):
        today = timezone.localdate()
        b = self.make_booking(today - timedelta(days=1), today + timedelta(days=1), room=self.other_room)
        res = self.client_a.post(self.url(b))
        self.assertEqual(res.status_code, 404)


# ── C4: financial gating ────────────────────────────────────────────────────────

class FinancialGatingTests(HardeningBase):
    def test_fin_c_price_edit_is_403_and_price_unchanged(self):
        res = self.post_json(self.client_c, self.room, {
            'action': 'update_details', 'price_per_night': '5000',
        })
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'error': 'No financial access.'})
        self.room.refresh_from_db()
        self.assertEqual(self.room.price_per_night, Decimal('1000.00'))

    def test_fin_c_edit_without_price_still_works(self):
        res = self.post_json(self.client_c, self.room, {
            'action': 'update_details', 'name': 'Renamed', 'capacity': 3,
        })
        self.assertEqual(res.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.name, 'Renamed')
        self.assertEqual(self.room.capacity, 3)
        self.assertEqual(self.room.price_per_night, Decimal('1000.00'))

    def test_fin_a_price_edit_works(self):
        res = self.post_json(self.client_a, self.room, {
            'action': 'update_details', 'price_per_night': '2500',
        })
        self.assertEqual(res.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.price_per_night, Decimal('2500.00'))

    def test_fin_b_price_edit_works(self):
        res = self.post_json(self.client_b, self.room, {
            'action': 'update_details', 'price_per_night': '1800',
        })
        self.assertEqual(res.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.price_per_night, Decimal('1800.00'))

    def test_fin_c_walk_in_price_override_is_403(self):
        res = self.client_c.post(
            reverse('employeeadmin:walk-in-booking-create'),
            self.walk_in_payload(price_override='1'),
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Booking.objects.filter(source='walk_in').count(), 0)

    def test_fin_c_walk_in_without_override_works(self):
        res = self.client_c.post(
            reverse('employeeadmin:walk-in-booking-create'), self.walk_in_payload(price_override=''),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(Booking.objects.filter(source='walk_in').count(), 1)

    def test_fin_a_walk_in_price_override_works(self):
        res = self.client_a.post(
            reverse('employeeadmin:walk-in-booking-create'),
            self.walk_in_payload(price_override='1234'),
        )
        self.assertEqual(res.status_code, 200, res.content)
        b = Booking.objects.get(source='walk_in')
        self.assertEqual(b.total_price, Decimal('1234'))

    def test_fin_c_room_create_is_403(self):
        res = self.client_c.post(reverse('employeeadmin:room-create'), {
            'property_id': str(self.prop_a.id), 'name': 'Nope',
            'room_type': 'double', 'price_per_night': '1200', 'capacity': '2',
        })
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'error': 'No financial access.'})
        self.assertFalse(Room.objects.filter(name='Nope').exists())

    def test_fin_b_room_create_works(self):
        res = self.client_b.post(reverse('employeeadmin:room-create'), {
            'property_id': str(self.prop_a.id), 'name': 'Allowed',
            'room_type': 'double', 'price_per_night': '1200', 'capacity': '2',
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(Room.objects.filter(name='Allowed').exists())

    def test_fin_c_seasonal_rate_still_403(self):
        res = self.client_c.post(reverse('employeeadmin:seasonal-rate-create'), {
            'room_id': str(self.room.id), 'start_date': '2030-01-01',
            'end_date': '2030-01-05', 'price': '900',
        })
        self.assertEqual(res.status_code, 403)


# ── H1: audit trail ─────────────────────────────────────────────────────────────

@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='ttr-hardening-media-'))
class AuditTrailTests(HardeningBase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def test_walk_in_create_is_audited(self):
        res = self.client_a.post(
            reverse('employeeadmin:walk-in-booking-create'),
            self.walk_in_payload(price_override='1500'),
        )
        self.assertEqual(res.status_code, 200, res.content)
        rows = self.audit_rows('WALK_IN_BOOKING_CREATED')
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.actor, self.emp_a)
        ref = res.json()['booking_reference']
        self.assertIn(ref, row.detail)
        self.assertIn('A1', row.detail)
        self.assertIn('cash', row.detail)
        self.assertIn('1500', row.detail)

    def test_failed_walk_in_is_not_audited(self):
        self.client_a.post(
            reverse('employeeadmin:walk-in-booking-create'), self.walk_in_payload(guests='0'),
        )
        self.assertEqual(self.audit_rows('WALK_IN_BOOKING_CREATED').count(), 0)

    def test_room_status_update_is_audited(self):
        res = self.client_a.post(
            reverse('employeeadmin:room-status-update', args=[self.room.id]),
            {'operational_status': 'maintenance'},
        )
        self.assertEqual(res.status_code, 200)
        row = self.audit_rows('ROOM_STATUS_UPDATED').get()
        self.assertIn('maintenance', row.detail)
        self.assertIn('A1', row.detail)

    def test_room_set_status_is_audited(self):
        res = self.post_json(self.client_a, self.room, {
            'action': 'set_status', 'operational_status': 'out_of_order',
        })
        self.assertEqual(res.status_code, 200)
        row = self.audit_rows('ROOM_STATUS_UPDATED').get()
        self.assertIn('out_of_order', row.detail)

    def test_block_create_and_delete_are_audited(self):
        res = self.client_a.post(reverse('employeeadmin:ota-block-create'), {
            'room_id': str(self.room.id), 'start_date': '2030-03-01',
            'end_date': '2030-03-04', 'reason': 'Painting',
        })
        self.assertEqual(res.status_code, 200)
        created = self.audit_rows('OTA_BLOCK_CREATED').get()
        self.assertIn('A1', created.detail)
        self.assertIn('2030-03-01', created.detail)
        self.assertIn('2030-03-04', created.detail)

        block_id = res.json()['id']
        res = self.client_a.post(reverse('employeeadmin:ota-block-delete', args=[block_id]))
        self.assertEqual(res.status_code, 200)
        deleted = self.audit_rows('OTA_BLOCK_DELETED').get()
        self.assertIn('A1', deleted.detail)
        self.assertIn('2030-03-01', deleted.detail)

    def test_seasonal_rate_create_is_audited(self):
        res = self.client_a.post(reverse('employeeadmin:seasonal-rate-create'), {
            'room_id': str(self.room.id), 'start_date': '2030-04-01',
            'end_date': '2030-04-10', 'price': '1750.50',
        })
        self.assertEqual(res.status_code, 200)
        row = self.audit_rows('ROOM_RATE_CREATED').get()
        self.assertIn('1750.50', row.detail)
        self.assertIn('2030-04-01', row.detail)
        self.assertIn('2030-04-10', row.detail)

    def test_room_create_is_audited(self):
        res = self.client_a.post(reverse('employeeadmin:room-create'), {
            'property_id': str(self.prop_a.id), 'name': 'Audited',
            'room_type': 'deluxe', 'price_per_night': '3000', 'capacity': '3',
        })
        self.assertEqual(res.status_code, 200)
        row = self.audit_rows('ROOM_CREATED').get()
        self.assertIn('Audited', row.detail)

    def test_room_edit_details_audited_with_price_change(self):
        res = self.post_json(self.client_a, self.room, {
            'action': 'update_details', 'price_per_night': '2000', 'name': 'A1x',
        })
        self.assertEqual(res.status_code, 200)
        row = self.audit_rows('ROOM_UPDATED').get()
        self.assertIn('1000', row.detail)
        self.assertIn('2000', row.detail)

    def test_room_edit_toggles_are_audited(self):
        self.post_json(self.client_a, self.room, {'action': 'toggle_active'})
        self.post_json(self.client_a, self.room, {'action': 'toggle_featured'})
        self.assertEqual(self.audit_rows('ROOM_UPDATED').count(), 2)

    def test_failed_edit_is_not_audited(self):
        self.post_json(self.client_c, self.room, {'action': 'update_details', 'price_per_night': '5'})
        self.post_json(self.client_a, self.room, {'action': 'update_details', 'capacity': '0'})
        self.assertEqual(self.audit_rows('ROOM_UPDATED').count(), 0)

    def test_image_upload_primary_delete_are_audited(self):
        up = reverse('employeeadmin:room-image-upload', args=[self.room.id])
        res = self.client_a.post(up, {
            'image': SimpleUploadedFile('a.gif', TINY_GIF, content_type='image/gif'),
            'is_primary': 'on',
        })
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.audit_rows('ROOM_IMAGE_UPLOADED').count(), 1)

        img = RoomImage.objects.get(room=self.room)
        res = self.client_a.post(reverse('employeeadmin:room-image-set-primary', args=[img.id]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.audit_rows('ROOM_IMAGE_PRIMARY_SET').count(), 1)

        res = self.client_a.post(reverse('employeeadmin:room-image-delete', args=[img.id]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.audit_rows('ROOM_IMAGE_DELETED').count(), 1)


# ── H2: bad input never 500s ────────────────────────────────────────────────────

class BadInputTests(HardeningBase):
    def create_payload(self, **overrides):
        data = {
            'property_id': str(self.prop_a.id), 'name': 'New',
            'room_type': 'double', 'price_per_night': '1200', 'capacity': '2',
        }
        data.update(overrides)
        return data

    def test_rooms_list_invalid_property_filter_is_ignored(self):
        res = self.client_a.get(reverse('employeeadmin:rooms'), {'property': 'abc'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.context['rooms']), 1)

    def test_availability_invalid_room_param_does_not_500(self):
        res = self.client_a.get(reverse('employeeadmin:availability'), {'room': 'abc'})
        self.assertLess(res.status_code, 500)

    def test_room_create_bad_numbers_are_400(self):
        url = reverse('employeeadmin:room-create')
        for overrides in (
            {'price_per_night': 'abc'}, {'price_per_night': 'NaN'}, {'price_per_night': 'Infinity'},
            {'price_per_night': ''}, {'capacity': 'x'}, {'capacity': ''}, {'rating': 'zzz'},
            {'property_id': 'not-a-uuid'}, {'name': ''},
        ):
            with self.subTest(overrides=overrides):
                res = self.client_a.post(url, self.create_payload(**overrides))
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn('error', res.json())
        self.assertFalse(Room.objects.filter(name='New').exists())

    def test_room_edit_malformed_json_is_400(self):
        url = reverse('employeeadmin:room-edit', args=[self.room.id])
        for body in ('{not json', '', '[1, 2]', '"str"'):
            with self.subTest(body=body):
                res = self.client_a.post(url, data=body, content_type='application/json')
                self.assertEqual(res.status_code, 400, res.content)

    def test_room_edit_bad_numbers_are_400(self):
        for payload in (
            {'price_per_night': 'abc'}, {'price_per_night': 'NaN'}, {'capacity': 'x'},
            {'capacity': '2.5x'}, {'rating': 'bad'}, {'price_per_night': {}},
        ):
            with self.subTest(payload=payload):
                res = self.post_json(self.client_a, self.room, {'action': 'update_details', **payload})
                self.assertEqual(res.status_code, 400, res.content)
        self.room.refresh_from_db()
        self.assertEqual(self.room.price_per_night, Decimal('1000.00'))

    def test_block_create_non_date_strings_are_400(self):
        url = reverse('employeeadmin:ota-block-create')
        for start, end in (('abc', '2030-01-05'), ('2030-01-01', 'xyz'), ('', ''), ('2030-13-45', '2030-14-01')):
            with self.subTest(start=start, end=end):
                res = self.client_a.post(url, {
                    'room_id': str(self.room.id), 'start_date': start, 'end_date': end,
                })
                self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(OTABlock.objects.count(), 0)

    def test_block_create_invalid_room_id_does_not_500(self):
        res = self.client_a.post(reverse('employeeadmin:ota-block-create'), {
            'room_id': 'not-a-uuid', 'start_date': '2030-01-01', 'end_date': '2030-01-05',
        })
        self.assertIn(res.status_code, (400, 404))

    def test_rate_create_bad_input_is_400(self):
        url = reverse('employeeadmin:seasonal-rate-create')
        base = {'room_id': str(self.room.id), 'start_date': '2030-01-01',
                'end_date': '2030-01-05', 'price': '900'}
        for overrides in (
            {'start_date': 'abc'}, {'end_date': 'abc'}, {'price': 'abc'}, {'price': 'NaN'},
            {'price': '0'}, {'price': '-5'}, {'price': ''},
        ):
            with self.subTest(overrides=overrides):
                res = self.client_a.post(url, {**base, **overrides})
                self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(RoomRate.objects.count(), 0)

    def test_rate_price_stored_as_exact_decimal(self):
        res = self.client_a.post(reverse('employeeadmin:seasonal-rate-create'), {
            'room_id': str(self.room.id), 'start_date': '2030-01-01',
            'end_date': '2030-01-05', 'price': '1234.57',
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(RoomRate.objects.get().price, Decimal('1234.57'))

    def test_walk_in_bad_guests_are_400(self):
        url = reverse('employeeadmin:walk-in-booking-create')
        for guests in ('0', '-1', 'abc', '1.5', ''):
            with self.subTest(guests=guests):
                res = self.client_a.post(url, self.walk_in_payload(guests=guests))
                self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(Booking.objects.filter(source='walk_in').count(), 0)

    def test_walk_in_bad_dates_and_override_are_400(self):
        url = reverse('employeeadmin:walk-in-booking-create')
        for overrides in (
            {'check_in': 'abc'}, {'check_out': ''}, {'price_override': 'abc'},
            {'price_override': '-5'}, {'price_override': 'NaN'}, {'room_id': 'zzz'},
        ):
            with self.subTest(overrides=overrides):
                res = self.client_a.post(url, self.walk_in_payload(**overrides))
                self.assertIn(res.status_code, (400, 404), res.content)

    def test_walk_in_guests_over_capacity_is_400(self):
        url = reverse('employeeadmin:walk-in-booking-create')
        res = self.client_a.post(url, self.walk_in_payload(guests='3'))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Booking.objects.filter(source='walk_in').count(), 0)

    def test_walk_in_guests_equal_capacity_ok(self):
        url = reverse('employeeadmin:walk-in-booking-create')
        res = self.client_a.post(url, self.walk_in_payload(guests='2'))
        self.assertEqual(res.status_code, 200, res.content)


# ── H6: Channex pushes ──────────────────────────────────────────────────────────

class ChannexPushTests(HardeningBase):
    PATCH = 'core.ota.dispatch.record_ari_change'

    def _assert_availability_push(self, mocked, room):
        mocked.assert_called()
        args, kwargs = mocked.call_args
        self.assertEqual(args[0], room.room_type)
        self.assertEqual(args[1], room.property_id)
        self.assertEqual(args[2], date.today())
        self.assertEqual(args[3], date.today() + timedelta(days=500))
        self.assertEqual(kwargs.get('change_types'), ('availability',))

    def test_room_create_pushes_availability(self):
        with mock.patch(self.PATCH) as m:
            res = self.client_a.post(reverse('employeeadmin:room-create'), {
                'property_id': str(self.prop_a.id), 'name': 'Pushy',
                'room_type': 'double', 'price_per_night': '1200', 'capacity': '2',
            })
        self.assertEqual(res.status_code, 200)
        room = Room.objects.get(name='Pushy')
        self._assert_availability_push(m, room)

    def test_toggle_active_pushes_availability(self):
        with mock.patch(self.PATCH) as m:
            res = self.post_json(self.client_a, self.room, {'action': 'toggle_active'})
        self.assertEqual(res.status_code, 200)
        self._assert_availability_push(m, self.room)

    def test_failed_room_create_does_not_push(self):
        with mock.patch(self.PATCH) as m:
            self.client_a.post(reverse('employeeadmin:room-create'), {
                'property_id': str(self.prop_a.id), 'name': 'Bad',
                'room_type': 'double', 'price_per_night': 'abc', 'capacity': '2',
            })
        m.assert_not_called()


# ── H7: room validation ─────────────────────────────────────────────────────────

class RoomValidationTests(HardeningBase):
    def create(self, **overrides):
        data = {
            'property_id': str(self.prop_a.id), 'name': 'Valid',
            'room_type': 'double', 'price_per_night': '1200', 'capacity': '2',
        }
        data.update(overrides)
        return self.client_a.post(reverse('employeeadmin:room-create'), data)

    def test_create_rejects_invalid_values(self):
        for overrides in (
            {'room_type': 'penthouse'}, {'room_type': ''},
            {'price_per_night': '0'}, {'price_per_night': '-10'},
            {'capacity': '0'}, {'capacity': '21'}, {'capacity': '-1'},
            {'rating': '5.1'}, {'rating': '-0.5'},
        ):
            with self.subTest(overrides=overrides):
                res = self.create(**overrides)
                self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(Room.objects.filter(name='Valid').exists())

    def test_create_accepts_boundaries(self):
        for i, overrides in enumerate((
            {'capacity': '1'}, {'capacity': '20'}, {'rating': '0'}, {'rating': '5'},
            {'room_type': 'single'}, {'room_type': 'deluxe'}, {'price_per_night': '0.01'},
        )):
            with self.subTest(overrides=overrides):
                res = self.create(name=f'Valid{i}', **overrides)
                self.assertEqual(res.status_code, 200, res.content)

    def test_update_rejects_invalid_values(self):
        for payload in (
            {'room_type': 'penthouse'}, {'price_per_night': '0'}, {'price_per_night': '-1'},
            {'capacity': '0'}, {'capacity': '21'}, {'rating': '6'}, {'rating': '-1'},
            {'name': '   '},
        ):
            with self.subTest(payload=payload):
                res = self.post_json(self.client_a, self.room, {'action': 'update_details', **payload})
                self.assertEqual(res.status_code, 400, res.content)
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacity, 2)
        self.assertEqual(self.room.name, 'A1')

    def test_update_is_all_or_nothing(self):
        res = self.post_json(self.client_a, self.room, {
            'action': 'update_details', 'name': 'Changed', 'capacity': '99',
        })
        self.assertEqual(res.status_code, 400)
        self.room.refresh_from_db()
        self.assertEqual(self.room.name, 'A1')

    def test_update_accepts_valid_values_and_blank_rating_resets(self):
        res = self.post_json(self.client_a, self.room, {
            'action': 'update_details', 'room_type': 'deluxe', 'capacity': '4', 'rating': None,
        })
        self.assertEqual(res.status_code, 200, res.content)
        self.room.refresh_from_db()
        self.assertEqual(self.room.capacity, 4)
        self.assertEqual(self.room.rating, Decimal('4.5'))


# ── M4: OTA block / rate ranges ─────────────────────────────────────────────────

class BlockAndRateRangeTests(HardeningBase):
    def block(self, start, end, room=None):
        return self.client_a.post(reverse('employeeadmin:ota-block-create'), {
            'room_id': str((room or self.room).id), 'start_date': start, 'end_date': end,
        })

    def rate(self, start, end, price='900'):
        return self.client_a.post(reverse('employeeadmin:seasonal-rate-create'), {
            'room_id': str(self.room.id), 'start_date': start, 'end_date': end, 'price': price,
        })

    def test_block_start_equal_end_rejected(self):
        res = self.block('2030-05-01', '2030-05-01')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(OTABlock.objects.count(), 0)

    def test_block_start_after_end_rejected(self):
        self.assertEqual(self.block('2030-05-05', '2030-05-01').status_code, 400)

    def test_block_one_night_ok(self):
        self.assertEqual(self.block('2030-05-01', '2030-05-02').status_code, 200)

    def test_block_overlapping_confirmed_booking_rejected_with_reference(self):
        b = self.make_booking(date(2030, 6, 10), date(2030, 6, 14))
        res = self.block('2030-06-12', '2030-06-20')
        self.assertEqual(res.status_code, 400)
        self.assertIn(b.booking_reference, res.json()['error'])
        self.assertEqual(OTABlock.objects.count(), 0)

    def test_block_containing_confirmed_booking_rejected(self):
        self.make_booking(date(2030, 6, 10), date(2030, 6, 14))
        self.assertEqual(self.block('2030-06-01', '2030-06-30').status_code, 400)

    def test_block_adjacent_to_booking_is_ok(self):
        self.make_booking(date(2030, 6, 10), date(2030, 6, 14))
        # Booking check-out is exclusive, so a block starting that day does not clash.
        self.assertEqual(self.block('2030-06-14', '2030-06-16').status_code, 200)
        self.assertEqual(self.block('2030-06-08', '2030-06-10').status_code, 200)

    def test_block_ignores_cancelled_booking(self):
        self.make_booking(date(2030, 6, 10), date(2030, 6, 14), status='cancelled')
        self.assertEqual(self.block('2030-06-11', '2030-06-12').status_code, 200)

    def test_block_ignores_other_rooms_bookings(self):
        self.make_booking(date(2030, 6, 10), date(2030, 6, 14), room=self.other_room)
        self.assertEqual(self.block('2030-06-11', '2030-06-12').status_code, 200)

    def test_rate_start_equal_end_rejected(self):
        res = self.rate('2030-05-01', '2030-05-01')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(RoomRate.objects.count(), 0)

    def test_rate_start_after_end_rejected(self):
        self.assertEqual(self.rate('2030-05-05', '2030-05-01').status_code, 400)

    def test_rate_valid_range_ok(self):
        self.assertEqual(self.rate('2030-05-01', '2030-05-05').status_code, 200)

    def test_rate_overlapping_booking_is_allowed(self):
        # Rates only affect future pricing; they are not an availability change.
        self.make_booking(date(2030, 6, 10), date(2030, 6, 14))
        self.assertEqual(self.rate('2030-06-01', '2030-06-30').status_code, 200)


# ── Low-severity items ──────────────────────────────────────────────────────────

class LowSeverityTests(HardeningBase):
    def set_status(self, status):
        return self.client_a.post(
            reverse('employeeadmin:room-status-update', args=[self.room.id]),
            {'operational_status': status},
        )

    def test_room_status_update_accepts_every_model_choice(self):
        for value, _ in Room.OPERATIONAL_STATUS_CHOICES:
            with self.subTest(value=value):
                self.assertEqual(self.set_status(value).status_code, 200)
                self.room.refresh_from_db()
                self.assertEqual(self.room.operational_status, value)

    def test_room_status_update_rejects_unknown_and_legacy_values(self):
        for value in ('needs_cleaning', 'bogus', ''):
            with self.subTest(value=value):
                self.assertEqual(self.set_status(value).status_code, 400)

    def test_room_images_get_unassigned_room_is_404(self):
        res = self.client_a.get(reverse('employeeadmin:room-images', args=[self.other_room.id]))
        self.assertEqual(res.status_code, 404)

    def test_room_images_get_assigned_room_is_200(self):
        res = self.client_a.get(reverse('employeeadmin:room-images', args=[self.room.id]))
        self.assertEqual(res.status_code, 200)
