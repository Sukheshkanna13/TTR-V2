from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import UserProfile
from loyalty.models import LoyaltyTier, LoyaltyConfig, CouponRedemptionRule, Coupon, LoyaltyLedger
from loyalty.services import (
    award_booking_points,
    redeem_points_for_coupon,
    apply_coupon_to_booking,
    remove_coupon_from_booking,
)
from payments.models import Payment
from payments.services import confirm_booking_and_payment
from rooms.models import Property, Room, Booking

User = get_user_model()


class LoyaltyCouponEngineTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="loyaltyguest@example.com",
            phone="+919876543210",
            password="strongpassword123",
            full_name="Loyalty Guest",
        )
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.loyalty_points = 500
        self.profile.save()

        self.property = Property.objects.create(
            name="Pondicherry Heritage",
            city="Pondicherry",
            address="12 White Town",
        )
        self.room = Room.objects.create(
            property=self.property,
            name="Deluxe Suite",
            room_type="deluxe",
            price_per_night=Decimal("2000.00"),
            capacity=2,
        )

        self.rule_fixed = CouponRedemptionRule.objects.create(
            name="₹250 Off Voucher",
            points_cost=200,
            discount_type="fixed",
            discount_value=Decimal("250.00"),
            min_booking_amount=Decimal("1000.00"),
            validity_days=30,
            is_active=True,
        )

        self.rule_percent = CouponRedemptionRule.objects.create(
            name="10% Off Voucher",
            points_cost=300,
            discount_type="percentage",
            discount_value=Decimal("10.00"),
            min_booking_amount=Decimal("1000.00"),
            max_discount_amount=Decimal("500.00"),
            validity_days=15,
            is_active=True,
        )

    def test_coupon_discount_calculation(self):
        # Fixed discount
        coupon = Coupon.objects.create(
            code="FIXED250",
            user=self.user,
            discount_type="fixed",
            discount_value=Decimal("250.00"),
            min_booking_amount=Decimal("1000.00"),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=30),
            status=Coupon.STATUS_ACTIVE,
        )
        # Below min booking amount
        self.assertEqual(coupon.calculate_discount(Decimal("800.00")), Decimal("0.00"))
        # Eligible booking
        self.assertEqual(coupon.calculate_discount(Decimal("4000.00")), Decimal("250.00"))

        # Percentage discount with cap
        coupon_pct = Coupon.objects.create(
            code="PCT10",
            user=self.user,
            discount_type="percentage",
            discount_value=Decimal("10.00"),
            min_booking_amount=Decimal("1000.00"),
            max_discount_amount=Decimal("300.00"),
            valid_from=timezone.now(),
            valid_until=timezone.now() + timedelta(days=30),
            status=Coupon.STATUS_ACTIVE,
        )
        # 10% of 2000 = 200
        self.assertEqual(coupon_pct.calculate_discount(Decimal("2000.00")), Decimal("200.00"))
        # 10% of 6000 = 600, capped at 300
        self.assertEqual(coupon_pct.calculate_discount(Decimal("6000.00")), Decimal("300.00"))

    def test_redeem_points_for_coupon_success(self):
        initial_pts = self.profile.loyalty_points
        success, coupon, msg = redeem_points_for_coupon(self.user, self.rule_fixed.id)
        self.assertTrue(success)
        self.assertIsNotNone(coupon)
        self.assertEqual(coupon.user, self.user)
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)
        self.assertEqual(coupon.discount_value, Decimal("250.00"))

        # Points debited
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.loyalty_points, initial_pts - 200)

        # Ledger row created
        ledger = LoyaltyLedger.objects.filter(user=self.user, reason="COUPON_REDEMPTION").first()
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.delta, -200)

    def test_redeem_points_insufficient_balance(self):
        self.profile.loyalty_points = 50
        self.profile.save()

        success, coupon, msg = redeem_points_for_coupon(self.user, self.rule_fixed.id)
        self.assertFalse(success)
        self.assertIsNone(coupon)
        self.assertIn("Insufficient points", msg)

    def test_apply_and_remove_coupon_on_booking(self):
        # Create booking hold
        booking = Booking.objects.create(
            user=self.user,
            room=self.room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            guests=2,
            total_price=Decimal("4000.00"),
            status="pending",
            hold_expires_at=timezone.now() + timedelta(minutes=10),
        )

        _, coupon, _ = redeem_points_for_coupon(self.user, self.rule_fixed.id)

        # Apply coupon
        success, msg, discount, payable = apply_coupon_to_booking(
            booking_id=booking.id,
            coupon_code=coupon.code,
            user=self.user,
        )
        self.assertTrue(success)
        self.assertEqual(discount, Decimal("250.00"))

        booking.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(booking.coupon, coupon)
        self.assertEqual(booking.discount_amount, Decimal("250.00"))
        self.assertEqual(coupon.status, Coupon.STATUS_APPLIED)
        self.assertEqual(booking.payable_amount, Decimal("3750.00"))

        # Remove coupon
        rem_success, rem_msg, new_payable = remove_coupon_from_booking(booking.id, user=self.user)
        self.assertTrue(rem_success)
        booking.refresh_from_db()
        coupon.refresh_from_db()
        self.assertIsNone(booking.coupon)
        self.assertEqual(booking.discount_amount, Decimal("0.00"))
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)
        self.assertEqual(booking.payable_amount, Decimal("4000.00"))

    def test_applied_coupon_auto_released_on_hold_expiry(self):
        booking = Booking.objects.create(
            user=self.user,
            room=self.room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            guests=2,
            total_price=Decimal("4000.00"),
            status="pending",
            hold_expires_at=timezone.now() - timedelta(seconds=1),  # already expired
        )
        _, coupon, _ = redeem_points_for_coupon(self.user, self.rule_fixed.id)
        coupon.status = Coupon.STATUS_APPLIED
        coupon.save()
        booking.coupon = coupon
        booking.save()

        # Check expire_if_needed
        expired = booking.expire_if_needed()
        self.assertTrue(expired)
        self.assertEqual(booking.status, "expired")

        coupon.refresh_from_db()
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)

    def test_applied_coupon_auto_released_on_release_hold(self):
        booking = Booking.objects.create(
            user=self.user,
            room=self.room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            guests=2,
            total_price=Decimal("4000.00"),
            status="pending",
            hold_expires_at=timezone.now() + timedelta(minutes=10),
        )
        _, coupon, _ = redeem_points_for_coupon(self.user, self.rule_fixed.id)
        coupon.status = Coupon.STATUS_APPLIED
        coupon.save()
        booking.coupon = coupon
        booking.save()

        # Guest abandons checkout / modal dismiss
        booking.release_hold(reason="abandoned")
        coupon.refresh_from_db()
        self.assertEqual(coupon.status, Coupon.STATUS_ACTIVE)

    def test_payment_confirmation_marks_coupon_redeemed(self):
        booking = Booking.objects.create(
            user=self.user,
            room=self.room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            guests=2,
            total_price=Decimal("4000.00"),
            status="pending",
            hold_expires_at=timezone.now() + timedelta(minutes=10),
            razorpay_order_id="order_test_12345",
        )
        Payment.objects.create(
            booking=booking,
            razorpay_order_id="order_test_12345",
            amount=Decimal("3750.00"),
            status="created",
        )

        _, coupon, _ = redeem_points_for_coupon(self.user, self.rule_fixed.id)
        apply_coupon_to_booking(booking.id, coupon.code, user=self.user)

        # Expected amount in paise: 3750.00 * 100 = 375000
        res = confirm_booking_and_payment(
            order_id="order_test_12345",
            payment_id="pay_test_98765",
            signature="test_sig",
            captured_amount_paise=375000,
            caller="test",
        )
        self.assertTrue(res["success"])

        booking.refresh_from_db()
        coupon.refresh_from_db()
        self.assertEqual(booking.status, "confirmed")
        self.assertEqual(coupon.status, Coupon.STATUS_REDEEMED)
        self.assertIsNotNone(coupon.used_at)

    def test_loyalty_apis(self):
        self.client.force_login(self.user, backend="accounts.backends.EmailBackend")

        # 1. My coupons API (initially empty)
        res = self.client.get("/loyalty/api/my-coupons/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["coupons"]), 0)

        # 2. Redeem API
        res = self.client.post(
            "/loyalty/api/redeem/",
            data={"rule_id": str(self.rule_fixed.id)},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        code = data["coupon"]["code"]

        # 3. My coupons API now has 1 coupon
        res = self.client.get("/loyalty/api/my-coupons/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["coupons"]), 1)

        # 4. Apply coupon API
        booking = Booking.objects.create(
            user=self.user,
            room=self.room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            guests=2,
            total_price=Decimal("4000.00"),
            status="pending",
            hold_expires_at=timezone.now() + timedelta(minutes=10),
        )
        res = self.client.post(
            "/loyalty/api/apply-coupon/",
            data={"booking_id": str(booking.id), "coupon_code": code},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        # 5. Remove coupon API
        res = self.client.post(
            "/loyalty/api/remove-coupon/",
            data={"booking_id": str(booking.id)},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

    def test_rewards_dashboard_view(self):
        self.client.force_login(self.user, backend="accounts.backends.EmailBackend")
        res = self.client.get("/loyalty/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Wayfarer Rewards")
        self.assertContains(res, "500")
        self.assertContains(res, "₹250 Off Voucher")
