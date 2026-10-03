from datetime import date, timedelta

from django.test import SimpleTestCase, override_settings
from rest_framework import serializers

from rooms.serializers import validate_booking_dates


@override_settings(MAX_STAY_NIGHTS=90, MAX_ADVANCE_BOOKING_DAYS=730)
class BookingDateLimitTests(SimpleTestCase):
    def test_normal_stay_is_accepted(self):
        start = date.today() + timedelta(days=10)
        validate_booking_dates(start, start + timedelta(days=3))

    def test_stay_at_the_limit_is_accepted(self):
        start = date.today() + timedelta(days=10)
        validate_booking_dates(start, start + timedelta(days=90))

    def test_stay_beyond_limit_is_rejected(self):
        start = date.today() + timedelta(days=10)
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_booking_dates(start, start + timedelta(days=91))
        self.assertIn("check_out", ctx.exception.detail)

    def test_absurd_far_future_range_is_rejected_quickly(self):
        with self.assertRaises(serializers.ValidationError):
            validate_booking_dates(date.today(), date(9999, 12, 31))

    def test_check_in_beyond_advance_window_is_rejected(self):
        start = date.today() + timedelta(days=731)
        with self.assertRaises(serializers.ValidationError) as ctx:
            validate_booking_dates(start, start + timedelta(days=2))
        self.assertIn("check_in", ctx.exception.detail)

    def test_existing_rules_still_apply(self):
        with self.assertRaises(serializers.ValidationError):
            validate_booking_dates(date.today() - timedelta(days=1), date.today() + timedelta(days=1))
        with self.assertRaises(serializers.ValidationError):
            validate_booking_dates(date.today() + timedelta(days=5), date.today() + timedelta(days=5))
