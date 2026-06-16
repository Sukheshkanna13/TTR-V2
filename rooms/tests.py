from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rooms.models import Room, Property, Booking, RoomImage

User = get_user_model()


def _guest(email='guest@test.com'):
    return User.objects.create_user(
        email=email, full_name='Guest', phone='7777777777',
        password='guestpass123', is_active=True,
    )


def _room():
    prop = Property.objects.create(name='P', city='Pondy', address='x', is_active=True)
    return Room.objects.create(
        property=prop, name='R', city='Pondy', room_type='single',
        price_per_night=Decimal('2000'), capacity=2, operational_status='available',
    )


def _hold(user, room, days_ahead=5, mins=10):
    today = timezone.now().date()
    ci = today + timedelta(days=days_ahead)
    return Booking.objects.create(
        room=room, user=user, check_in=ci, check_out=ci + timedelta(days=2),
        guests=1, total_price=Decimal('4000'), status='pending',
        hold_expires_at=timezone.now() + timedelta(minutes=mins),
    )


class ReleaseHoldModelTest(TestCase):
    def test_release_pending_sets_expired_and_clears_expiry(self):
        b = _hold(_guest(), _room())
        self.assertTrue(b.release_hold('abandoned'))
        b.refresh_from_db()
        self.assertEqual(b.status, 'expired')
        self.assertIsNone(b.hold_expires_at)

    def test_release_payment_failed_marks_failed(self):
        b = _hold(_guest(), _room())
        b.release_hold('payment_failed')
        b.refresh_from_db()
        self.assertEqual(b.status, 'failed')

    def test_release_is_noop_on_confirmed(self):
        b = _hold(_guest(), _room())
        b.status = 'confirmed'
        b.save(update_fields=['status'])
        self.assertFalse(b.release_hold('abandoned'))
        b.refresh_from_db()
        self.assertEqual(b.status, 'confirmed')


class ReleaseHoldEndpointTest(TestCase):
    def setUp(self):
        self.user = _guest()
        self.client = Client()
        self.client.force_login(self.user)
        self.room = _room()

    def test_release_frees_the_room(self):
        b = _hold(self.user, self.room)
        res = self.client.post(reverse('bookings:release', args=[b.id]))
        self.assertEqual(res.status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.status, 'expired')

    def test_release_is_idempotent(self):
        b = _hold(self.user, self.room)
        self.client.post(reverse('bookings:release', args=[b.id]))
        res = self.client.post(reverse('bookings:release', args=[b.id]))
        self.assertEqual(res.status_code, 200)

    def test_cannot_release_another_users_hold(self):
        other = _guest('other@test.com')
        b = _hold(other, self.room)
        res = self.client.post(reverse('bookings:release', args=[b.id]))
        self.assertEqual(res.status_code, 404)
        b.refresh_from_db()
        self.assertEqual(b.status, 'pending')


class SameUserReclaimTest(TestCase):
    def setUp(self):
        self.user = _guest()
        self.client = Client()
        self.client.force_login(self.user)
        self.room = _room()

    def test_same_user_rebook_reuses_own_hold_not_409(self):
        existing = _hold(self.user, self.room)
        payload = {
            'room_id': str(self.room.id),
            'check_in': existing.check_in.isoformat(),
            'check_out': existing.check_out.isoformat(),
            'guests': 1,
        }
        res = self.client.post(reverse('bookings:hold'), data=payload, content_type='application/json')
        self.assertIn(res.status_code, (200, 201))
        # No second pending hold should be created for the same room+dates
        pend = Booking.objects.filter(room=self.room, user=self.user, status='pending').count()
        self.assertEqual(pend, 1)


class RoomOperationalStatusTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name='Test Prop', city='Pondy', is_active=True)
        self.room = Room.objects.create(
            property=self.prop,
            name='R1',
            city='Pondy',
            room_type='single',
            price_per_night=2000,
            capacity=2,
        )

    def test_default_status_is_available(self):
        self.assertEqual(self.room.operational_status, 'available')

    def test_all_four_statuses_accept(self):
        for status in ['available', 'cleaning', 'maintenance', 'out_of_order']:
            self.room.operational_status = status
            self.room.full_clean()
            self.room.save()
            self.assertEqual(Room.objects.get(pk=self.room.pk).operational_status, status)


def _frprop(name, rating='4.5'):
    return Property.objects.create(
        name=name, city='Pondy', address='addr', is_active=True, rating=rating,
    )


def _frroom(prop, name='R', featured=False, active=True,
            status='available', with_image=True):
    room = Room.objects.create(
        property=prop, name=name, city='Pondy', room_type='single',
        price_per_night=Decimal('2000'), capacity=2,
        operational_status=status, is_active=active, is_featured=featured,
    )
    if with_image:
        RoomImage.objects.create(room=room, image='room_images/x.jpg')
    return room


class FeaturedForHomeTest(TestCase):
    def test_no_featured_returns_three_highest_rated(self):
        a = _frroom(_frprop('A', '4.9'), name='A')
        b = _frroom(_frprop('B', '4.8'), name='B')
        c = _frroom(_frprop('C', '4.7'), name='C')
        _frroom(_frprop('D', '4.6'), name='D')
        result = Room.objects.featured_for_home()
        self.assertEqual([r.id for r in result], [a.id, b.id, c.id])

    def test_fewer_than_three_featured_fills_to_three(self):
        low = _frroom(_frprop('Low', '4.0'), name='Low', featured=True)
        a = _frroom(_frprop('A', '4.9'), name='A')
        b = _frroom(_frprop('B', '4.8'), name='B')
        result = Room.objects.featured_for_home()
        self.assertEqual(result[0].id, low.id)          # featured first
        self.assertEqual({r.id for r in result}, {low.id, a.id, b.id})
        self.assertEqual(len(result), 3)

    def test_three_or_more_featured_returns_all(self):
        rooms = [_frroom(_frprop(f'P{i}', '4.5'), name=f'F{i}', featured=True)
                 for i in range(4)]
        result = Room.objects.featured_for_home()
        self.assertEqual(len(result), 4)
        self.assertEqual({r.id for r in result}, {r.id for r in rooms})

    def test_imageless_featured_room_excluded(self):
        no_img = _frroom(_frprop('NoImg', '5.0'), name='NoImg',
                         featured=True, with_image=False)
        a = _frroom(_frprop('A', '4.9'), name='A')
        b = _frroom(_frprop('B', '4.8'), name='B')
        c = _frroom(_frprop('C', '4.7'), name='C')
        result = Room.objects.featured_for_home()
        self.assertNotIn(no_img.id, [r.id for r in result])
        self.assertEqual({r.id for r in result}, {a.id, b.id, c.id})

    def test_inactive_and_unavailable_excluded(self):
        inactive = _frroom(_frprop('In', '5.0'), name='In', active=False)
        cleaning = _frroom(_frprop('Cl', '5.0'), name='Cl', status='cleaning')
        a = _frroom(_frprop('A', '4.9'), name='A')
        b = _frroom(_frprop('B', '4.8'), name='B')
        c = _frroom(_frprop('C', '4.7'), name='C')
        result_ids = [r.id for r in Room.objects.featured_for_home()]
        self.assertNotIn(inactive.id, result_ids)
        self.assertNotIn(cleaning.id, result_ids)
        self.assertEqual(set(result_ids), {a.id, b.id, c.id})
