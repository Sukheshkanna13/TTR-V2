"""
Regression tests for the rooms-domain findings of the admin panels audit
(docs/ADMIN-PANELS-AUDIT-2026-10-18.md): H3 (walk-in validation) and
H4 (invalid room status written by auto_complete_bookings).
"""
import importlib
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import UserProfile
from payments.models import Payment
from rooms.models import Booking, Property, Room
from rooms.services import create_walk_in_booking
from rooms.tasks import auto_complete_bookings

User = get_user_model()


def make_user(email, phone, role, **extra):
    user = User.objects.create_user(
        email=email, full_name="Someone", phone=phone, is_active=True, **extra
    )
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = role
    profile.save()
    return user


class RoomFixtureMixin:
    def setUp(self):
        super().setUp()
        self.prop = Property.objects.create(
            name="Pondy Resort", city="Pondy", address="Beach Rd", is_active=True
        )
        self.room = Room.objects.create(
            property=self.prop, name="Deluxe 101", city="Pondy", room_type="deluxe",
            price_per_night=Decimal("3000"), capacity=2, is_active=True,
        )
        self.today = timezone.localdate()
        self.guest = make_user("guest@example.com", "9000000001", "guest")

    def make_booking(self, check_in, check_out, status="confirmed", room=None):
        return Booking.objects.create(
            room=room or self.room, user=self.guest, guest_name="G",
            guest_phone="9000000001", check_in=check_in, check_out=check_out,
            guests=1, status=status, total_price=Decimal("3000"),
        )


class AutoCompleteBookingsRoomStatusTests(RoomFixtureMixin, TestCase):
    def test_sets_valid_cleaning_status(self):
        b = self.make_booking(self.today - timedelta(days=3), self.today - timedelta(days=1))
        self.assertEqual(auto_complete_bookings(), 1)
        self.room.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(self.room.operational_status, Room.STATUS_CLEANING)
        self.assertEqual(self.room.operational_status, "cleaning")
        self.assertEqual(b.status, "completed")

    def test_room_left_alone_when_another_stay_in_progress(self):
        old = self.make_booking(self.today - timedelta(days=3), self.today - timedelta(days=1))
        current = self.make_booking(self.today - timedelta(days=1), self.today + timedelta(days=2))
        auto_complete_bookings()
        self.room.refresh_from_db()
        old.refresh_from_db()
        current.refresh_from_db()
        self.assertEqual(self.room.operational_status, Room.STATUS_AVAILABLE)
        self.assertEqual(old.status, "completed")
        self.assertEqual(current.status, "confirmed")

    def test_room_left_alone_when_guest_checks_in_today(self):
        self.make_booking(self.today - timedelta(days=3), self.today - timedelta(days=1))
        self.make_booking(self.today, self.today + timedelta(days=1))
        auto_complete_bookings()
        self.room.refresh_from_db()
        self.assertEqual(self.room.operational_status, Room.STATUS_AVAILABLE)

    def test_future_booking_does_not_prevent_cleaning(self):
        self.make_booking(self.today - timedelta(days=3), self.today - timedelta(days=1))
        self.make_booking(self.today + timedelta(days=5), self.today + timedelta(days=6))
        auto_complete_bookings()
        self.room.refresh_from_db()
        self.assertEqual(self.room.operational_status, Room.STATUS_CLEANING)


class NeedsCleaningMigrationTests(RoomFixtureMixin, TestCase):
    def test_migration_rewrites_needs_cleaning_rows(self):
        other = Room.objects.create(
            property=self.prop, name="Deluxe 102", city="Pondy", room_type="deluxe",
            price_per_night=Decimal("3000"), capacity=2, operational_status="maintenance",
        )
        # Bypass choice validation, as the buggy task did.
        Room.objects.filter(pk=self.room.pk).update(operational_status="needs_cleaning")

        migration = importlib.import_module("rooms.migrations.0025_fix_needs_cleaning_status")
        migration.fix_needs_cleaning(apps, None)

        self.room.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.room.operational_status, "cleaning")
        self.assertEqual(other.operational_status, "maintenance")
        self.assertFalse(Room.objects.filter(operational_status="needs_cleaning").exists())


@mock.patch("rooms.services.async_task")
class WalkInValidationTests(RoomFixtureMixin, TestCase):
    def walk_in(self, **overrides):
        kwargs = dict(
            room=self.room,
            check_in=self.today + timedelta(days=1),
            check_out=self.today + timedelta(days=3),
            guests=2,
            guest_name="Walk In",
            guest_phone="9111111111",
            guest_email="walkin@example.com",
        )
        kwargs.update(overrides)
        return create_walk_in_booking(**kwargs)

    def assertRejected(self, **overrides):
        with self.assertRaises(ValueError):
            self.walk_in(**overrides)
        self.assertFalse(Booking.objects.filter(source=Booking.SOURCE_WALK_IN).exists())
        self.assertFalse(Payment.objects.exists())

    def test_happy_path(self, _async):
        booking = self.walk_in(payment_method=Payment.METHOD_CASH)
        self.assertEqual(booking.status, "confirmed")
        self.assertEqual(booking.total_price, Decimal("6000"))
        self.assertEqual(booking.user.email, "walkin@example.com")
        self.assertEqual(booking.user.userprofile.role, "guest")
        payment = Payment.objects.get(booking=booking)
        self.assertEqual(payment.status, "captured")

    def test_positive_price_override_applies(self, _async):
        booking = self.walk_in(price_override=Decimal("4500"))
        self.assertEqual(booking.total_price, Decimal("4500"))

    def test_pay_at_checkout_is_not_captured(self, _async):
        booking = self.walk_in(payment_method=Payment.METHOD_PAY_AT_CHECKOUT)
        self.assertEqual(Payment.objects.get(booking=booking).status, "created")

    def test_invalid_payment_method_rejected(self, _async):
        self.assertRejected(payment_method="bitcoin")

    def test_zero_guests_rejected(self, _async):
        self.assertRejected(guests=0)

    def test_guests_over_capacity_rejected(self, _async):
        self.assertRejected(guests=self.room.capacity + 1)

    def test_guests_at_capacity_accepted(self, _async):
        self.assertEqual(self.walk_in(guests=self.room.capacity).guests, 2)

    def test_negative_price_override_rejected(self, _async):
        self.assertRejected(price_override=Decimal("-500"))

    def test_zero_price_override_rejected(self, _async):
        self.assertRejected(price_override=Decimal("0"))

    def test_inactive_room_rejected(self, _async):
        Room.objects.filter(pk=self.room.pk).update(is_active=False)
        self.room.refresh_from_db()
        self.assertRejected()

    def test_inactive_room_rejected_even_with_stale_instance(self, _async):
        stale = Room.objects.get(pk=self.room.pk)
        Room.objects.filter(pk=self.room.pk).update(is_active=False)
        with self.assertRaises(ValueError):
            self.walk_in(room=stale)

    def test_existing_guest_matched_by_email(self, _async):
        booking = self.walk_in(guest_email="guest@example.com", guest_phone="9222222222")
        self.assertEqual(booking.user, self.guest)

    def test_existing_guest_matched_by_phone(self, _async):
        booking = self.walk_in(guest_email="", guest_phone="9000000001")
        self.assertEqual(booking.user, self.guest)

    def test_staff_email_not_matched(self, _async):
        staff = make_user("staff@example.com", "9333333333", "employee_admin", is_staff=True)
        booking = self.walk_in(guest_email="staff@example.com", guest_phone="9444444444")
        self.assertNotEqual(booking.user, staff)
        self.assertEqual(booking.user.userprofile.role, "guest")
        self.assertTrue(booking.user.email.endswith("@guest.templeandtowns.in"))
        self.assertEqual(booking.guest_email, "staff@example.com")
        self.assertEqual(User.objects.filter(email="staff@example.com").count(), 1)

    def test_staff_phone_not_matched(self, _async):
        staff = make_user("boss@example.com", "9555555555", "super_admin", is_staff=True)
        booking = self.walk_in(guest_email="", guest_phone="9555555555")
        self.assertNotEqual(booking.user, staff)
        self.assertEqual(booking.user.userprofile.role, "guest")

    def test_user_without_profile_not_matched(self, _async):
        orphan = User.objects.create_user(
            email="orphan@example.com", full_name="O", phone="9666666666", is_active=True
        )
        UserProfile.objects.filter(user=orphan).delete()
        booking = self.walk_in(guest_email="orphan@example.com", guest_phone="9777777777")
        self.assertNotEqual(booking.user, orphan)
