from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from payments.admin import PaymentAdmin, ProcessedWebhookEventAdmin
from payments.models import Payment, ProcessedWebhookEvent
from rooms.models import Booking, Property, Room

User = get_user_model()


class PaymentAdminTest(TestCase):
    def test_payment_admin_registration_and_fields(self):
        self.assertIn(Payment, admin.site._registry)
        model_admin = admin.site._registry[Payment]
        self.assertIsInstance(model_admin, PaymentAdmin)

        # Verify task A3 fields in list_display
        self.assertIn("payment_method", model_admin.list_display)
        self.assertIn("refund_status", model_admin.list_display)

        # Verify list_filter and search_fields
        self.assertIn("payment_method", model_admin.list_filter)
        self.assertIn("refund_status", model_admin.list_filter)
        self.assertIn("refund_id", model_admin.search_fields)

        # Verify fieldsets contain refund and payment_method
        all_fieldset_fields = []
        for _name, opts in model_admin.fieldsets:
            all_fieldset_fields.extend(opts.get("fields", ()))
        self.assertIn("payment_method", all_fieldset_fields)
        self.assertIn("refund_id", all_fieldset_fields)
        self.assertIn("refund_status", all_fieldset_fields)

    def test_processed_webhook_event_admin_registered(self):
        self.assertIn(ProcessedWebhookEvent, admin.site._registry)
        model_admin = admin.site._registry[ProcessedWebhookEvent]
        self.assertIsInstance(model_admin, ProcessedWebhookEventAdmin)
        self.assertIn("source", model_admin.list_display)
        self.assertIn("event_id", model_admin.list_display)
        self.assertIn("processed_at", model_admin.list_display)


class CheckoutPrefillTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="arjun@test.com",
            full_name="Arjun Sharma",
            phone="9876543210",
            password="testpassword123",
            is_active=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.prop = Property.objects.create(name="Resort P", city="Pondy", address="Beach road", is_active=True)
        self.room = Room.objects.create(
            property=self.prop,
            name="Sea View Villa",
            city="Pondy",
            room_type="villa",
            price_per_night=Decimal("5000"),
            capacity=2,
            operational_status="available",
        )
        today = timezone.now().date()
        self.booking = Booking.objects.create(
            room=self.room,
            user=self.user,
            check_in=today + timezone.timedelta(days=2),
            check_out=today + timezone.timedelta(days=4),
            guests=2,
            total_price=Decimal("10000"),
            status="pending",
            hold_expires_at=timezone.now() + timezone.timedelta(minutes=10),
        )

    def test_checkout_page_renders_user_prefill_vars(self):
        res = self.client.get(reverse("payments:checkout-page") + f"?booking_id={self.booking.id}")
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("Arjun Sharma", content)
        self.assertIn("arjun@test.com", content)
        self.assertIn("9876543210", content)

    @patch("payments.views.create_razorpay_order")
    def test_create_order_api_returns_user_prefill_details(self, mock_create_order):
        mock_create_order.return_value = {
            "id": "order_test_12345",
            "amount": 1000000,
            "currency": "INR",
        }
        res = self.client.post(
            reverse("payments:create-order"),
            data={"booking_id": str(self.booking.id)},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("user", data)
        self.assertEqual(data["user"]["name"], "Arjun Sharma")
        self.assertEqual(data["user"]["email"], "arjun@test.com")
        self.assertEqual(data["user"]["phone"], "9876543210")
