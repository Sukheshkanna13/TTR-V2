"""
A coupon reserved on a hold ("applied") must return to "active" whenever that
hold ends without payment, by any route. Otherwise a guest permanently loses a
coupon they may have bought with loyalty points.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import UserProfile
from loyalty.models import Coupon
from loyalty.services import apply_coupon_to_booking
from rooms.models import Booking, Property, Room
from rooms.tasks import release_expired_holds

User = get_user_model()


class CouponReleaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="guest@example.com", phone="+919876543210",
            password="strongpassword123", full_name="Guest", is_active=True,
        )
        UserProfile.objects.get_or_create(user=self.user)
        prop = Property.objects.create(name="Pondy", city="Pondicherry", address="12 White Town")
        self.room = Room.objects.create(
            property=prop, name="Deluxe", room_type="deluxe",
            price_per_night=Decimal("2000.00"), capacity=2,
        )

    def _booking(self, hold_offset_minutes, status="pending", user=None):
        return Booking.objects.create(
            user=user or self.user, room=self.room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            guests=2, total_price=Decimal("4000.00"), status=status,
            hold_expires_at=timezone.now() + timedelta(minutes=hold_offset_minutes),
        )

    def _applied_coupon(self, booking, code="APPLIED1", user=None):
        coupon = Coupon.objects.create(
            code=code, user=user or self.user, discount_type="fixed",
            discount_value=Decimal("250.00"), min_booking_amount=Decimal("1000.00"),
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=30),
            status=Coupon.STATUS_APPLIED,
        )
        booking.coupon = coupon
        booking.discount_amount = Decimal("250.00")
        booking.save(update_fields=["coupon", "discount_amount"])
        return coupon

    def test_sweep_releases_coupon_of_expired_hold(self):
        booking = self._booking(hold_offset_minutes=-1)
        coupon = self._applied_coupon(booking)

        release_expired_holds()

        booking.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(booking.status, "expired")
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)

    def test_sweep_keeps_coupon_of_live_hold(self):
        booking = self._booking(hold_offset_minutes=5)
        coupon = self._applied_coupon(booking)

        release_expired_holds()

        booking.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(booking.status, "pending")
        self.assertEqual(coupon.status, Coupon.STATUS_APPLIED)

    def test_sweep_repairs_coupon_stuck_on_a_dead_booking(self):
        booking = self._booking(hold_offset_minutes=-30, status="expired")
        coupon = self._applied_coupon(booking)  # stuck by the old sweep

        release_expired_holds()

        coupon.refresh_from_db()
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)

    def test_guest_cancelling_pending_booking_releases_coupon(self):
        booking = self._booking(hold_offset_minutes=5)
        coupon = self._applied_coupon(booking)
        client = Client()
        client.force_login(self.user)

        response = client.post(f"/bookings/{booking.id}/cancel/")

        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(booking.status, "cancelled")
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)

    def test_superadmin_cancelling_pending_booking_releases_coupon(self):
        booking = self._booking(hold_offset_minutes=5)
        coupon = self._applied_coupon(booking)
        admin = User.objects.create_superuser(
            email="root@example.com", password="strongpassword123", full_name="Root",
        )
        client = Client()
        client.force_login(admin)

        response = client.post(f"/super-admin/bookings/{booking.id}/cancel/")

        self.assertEqual(response.status_code, 200)
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)

    def test_cannot_apply_coupon_to_someone_elses_booking(self):
        other = User.objects.create_user(
            email="other@example.com", phone="+919800000000",
            password="strongpassword123", full_name="Other", is_active=True,
        )
        victim_booking = self._booking(hold_offset_minutes=5, user=other)
        mine = Coupon.objects.create(
            code="MINE250", user=self.user, discount_type="fixed",
            discount_value=Decimal("250.00"), min_booking_amount=Decimal("1000.00"),
            valid_from=timezone.now() - timedelta(days=1),
            valid_until=timezone.now() + timedelta(days=30),
            status=Coupon.STATUS_ACTIVE,
        )

        ok, msg, _, _ = apply_coupon_to_booking(victim_booking.id, "MINE250", user=self.user)

        self.assertFalse(ok)
        mine.refresh_from_db()
        victim_booking.refresh_from_db()
        self.assertEqual(mine.status, Coupon.STATUS_ACTIVE)
        self.assertIsNone(victim_booking.coupon)
