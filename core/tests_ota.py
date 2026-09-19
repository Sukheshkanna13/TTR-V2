import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.utils import timezone

from core.ota.channex import ChannexManager
from core.ota.processor import process_channex_webhook
from payments.models import Payment
from rooms.models import Booking, Property, Room

User = get_user_model()


class ChannexManagerTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name="Pondy Resort", city="Pondy", address="Beach Rd", is_active=True)
        self.room1 = Room.objects.create(
            property=self.prop, name="Deluxe 101", city="Pondy", room_type="deluxe",
            price_per_night=Decimal("3000"), capacity=2, is_active=True,
        )
        self.room2 = Room.objects.create(
            property=self.prop, name="Deluxe 102", city="Pondy", room_type="deluxe",
            price_per_night=Decimal("3000"), capacity=2, is_active=True,
        )

    def test_verify_signature(self):
        manager = ChannexManager(webhook_secret="secret_test_key")
        body = b'{"event": "booking.created"}'
        expected = hmac.new(b"secret_test_key", body, hashlib.sha256).hexdigest()

        self.assertTrue(manager.verify_signature(body, expected))
        self.assertTrue(manager.verify_signature(body, f"sha256={expected}"))
        self.assertFalse(manager.verify_signature(body, "invalid_sig"))

    def test_calculate_available_count(self):
        today = timezone.now().date()
        ci = today + timedelta(days=5)
        co = today + timedelta(days=7)

        # Initially 2 rooms available
        avail = ChannexManager.calculate_available_count("deluxe", ci, co, property_id=self.prop.id)
        self.assertEqual(avail, 2)

        # Book 1 room
        user = User.objects.create_user(email="testuser@example.com", phone="9999999999", full_name="User")
        Booking.objects.create(
            room=self.room1, user=user, check_in=ci, check_out=co,
            guests=2, total_price=Decimal("6000"), status="confirmed",
        )

        avail_after = ChannexManager.calculate_available_count("deluxe", ci, co, property_id=self.prop.id)
        self.assertEqual(avail_after, 1)

    def test_push_inventory_dry_run(self):
        manager = ChannexManager(api_key="")
        res = manager.push_inventory("deluxe", timezone.now().date(), timezone.now().date() + timedelta(days=2), 5)
        self.assertTrue(res["success"])
        self.assertTrue(res.get("dry_run"))

    def test_sync_ota_inventory_for_dates_task(self):
        from rooms.tasks import sync_ota_inventory_for_dates
        today = timezone.now().date()
        ci = (today + timedelta(days=3)).isoformat()
        co = (today + timedelta(days=5)).isoformat()
        success = sync_ota_inventory_for_dates("deluxe", ci, co, property_id=self.prop.id)
        self.assertTrue(success)


class ChannexWebhookProcessorTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name="Bengaluru Stay", city="Bengaluru", address="MG Rd", is_active=True)
        self.room_a = Room.objects.create(
            property=self.prop, name="Suite A", city="Bengaluru", room_type="deluxe",
            price_per_night=Decimal("4000"), capacity=2, is_active=True,
        )
        self.room_b = Room.objects.create(
            property=self.prop, name="Suite B", city="Bengaluru", room_type="deluxe",
            price_per_night=Decimal("4000"), capacity=2, is_active=True,
        )

    def test_booking_created_webhook(self):
        today = timezone.now().date()
        payload = {
            "event": "booking.created",
            "booking": {
                "id": "chx_res_001",
                "channel": "Booking.com",
                "check_in": (today + timedelta(days=10)).isoformat(),
                "check_out": (today + timedelta(days=12)).isoformat(),
                "room_type": "deluxe",
                "property_id": str(self.prop.id),
                "guests": 2,
                "total_price": "8000.00",
                "customer": {
                    "name": "Alex Smith",
                    "email": "alex@ota-travel.com",
                    "phone": "9812345678",
                },
                "notes": "Late check-in requested",
            },
        }

        result = process_channex_webhook("booking.created", payload)
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "created")

        # Verify DB records
        booking = Booking.objects.get(ota_reservation_id="chx_res_001")
        self.assertEqual(booking.status, "confirmed")
        self.assertEqual(booking.source, Booking.SOURCE_OTA_BOOKING_COM)
        self.assertEqual(booking.guest_name, "Alex Smith")
        self.assertEqual(booking.guest_email, "alex@ota-travel.com")
        self.assertEqual(booking.total_price, Decimal("8000.00"))
        self.assertTrue(booking.booking_reference.startswith(f"TT-{timezone.now().year}-"))
        self.assertIn("Late check-in requested", booking.operational_notes)

        # Payment record created
        payment = Payment.objects.get(booking=booking)
        self.assertEqual(payment.status, "captured")
        self.assertEqual(payment.amount, Decimal("8000.00"))

        # Idempotency check
        repeat_result = process_channex_webhook("booking.created", payload)
        self.assertTrue(repeat_result["success"])
        self.assertEqual(repeat_result["action"], "already_exists")

    def test_booking_modified_webhook_reallocates_conflicted_room(self):
        today = timezone.now().date()
        orig_ci = today + timedelta(days=10)
        orig_co = today + timedelta(days=12)

        # Initial booking in room_a
        create_payload = {
            "event": "booking.created",
            "booking": {
                "id": "chx_res_002",
                "channel": "Agoda",
                "check_in": orig_ci.isoformat(),
                "check_out": orig_co.isoformat(),
                "room_type": "deluxe",
                "property_id": str(self.prop.id),
                "guests": 2,
                "total_price": "8000.00",
                "customer": {"name": "Bob Taylor", "email": "bob@travel.com"},
            },
        }
        process_channex_webhook("booking.created", create_payload)
        booking = Booking.objects.get(ota_reservation_id="chx_res_002")
        assigned_room = booking.room

        # Now, block assigned_room on the new shifted dates (days 14..16) with another booking
        shifted_ci = today + timedelta(days=14)
        shifted_co = today + timedelta(days=16)
        other_user = User.objects.create_user(email="other@user.com", phone="8888888888", full_name="Other")
        Booking.objects.create(
            room=assigned_room, user=other_user, check_in=shifted_ci, check_out=shifted_co,
            guests=1, total_price=Decimal("8000.00"), status="confirmed",
        )

        # Inbound date modification from OTA
        modify_payload = {
            "event": "booking.modified",
            "booking": {
                "id": "chx_res_002",
                "check_in": shifted_ci.isoformat(),
                "check_out": shifted_co.isoformat(),
                "total_price": "8500.00",
            },
        }
        mod_res = process_channex_webhook("booking.modified", modify_payload)
        self.assertTrue(mod_res["success"])
        self.assertTrue(mod_res["dates_changed"])
        self.assertTrue(mod_res["room_reallocated"])

        booking.refresh_from_db()
        self.assertEqual(booking.check_in, shifted_ci)
        self.assertEqual(booking.check_out, shifted_co)
        self.assertEqual(booking.total_price, Decimal("8500.00"))
        # Room must have changed to room_b because assigned_room was blocked on shifted dates
        self.assertNotEqual(booking.room, assigned_room)
        self.assertIn("[OTA DATE MODIFICATION]", booking.operational_notes)

    def test_booking_cancelled_webhook(self):
        today = timezone.now().date()
        create_payload = {
            "event": "booking.created",
            "booking": {
                "id": "chx_res_003",
                "channel": "MakeMyTrip",
                "check_in": (today + timedelta(days=20)).isoformat(),
                "check_out": (today + timedelta(days=22)).isoformat(),
                "room_type": "deluxe",
                "property_id": str(self.prop.id),
                "guests": 1,
                "total_price": "8000.00",
                "customer": {"name": "Charlie", "email": "charlie@travel.com"},
            },
        }
        process_channex_webhook("booking.created", create_payload)

        cancel_payload = {
            "event": "booking.cancelled",
            "booking": {"id": "chx_res_003"},
        }
        cancel_res = process_channex_webhook("booking.cancelled", cancel_payload)
        self.assertTrue(cancel_res["success"])
        self.assertEqual(cancel_res["action"], "cancelled")

        booking = Booking.objects.get(ota_reservation_id="chx_res_003")
        self.assertEqual(booking.status, "cancelled")
        self.assertIn("[OTA CANCELLATION]", booking.operational_notes)


@override_settings(CHANNEX_WEBHOOK_SECRET="test_secret_123")
class ChannexWebhookHttpTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.prop = Property.objects.create(name="Auroville Sanctuary", city="Auroville", address="Peace Rd", is_active=True)
        self.room = Room.objects.create(
            property=self.prop, name="Peace Hut", city="Auroville", room_type="single",
            price_per_night=Decimal("2000"), capacity=1, is_active=True,
        )

    def test_webhook_post_with_valid_signature(self):
        today = timezone.now().date()
        payload_dict = {
            "event": "booking.created",
            "booking": {
                "id": "http_test_001",
                "channel": "Airbnb",
                "check_in": (today + timedelta(days=30)).isoformat(),
                "check_out": (today + timedelta(days=32)).isoformat(),
                "room_type": "single",
                "property_id": str(self.prop.id),
                "guests": 1,
                "total_price": "4000.00",
                "customer": {"name": "David", "email": "david@bnb.com"},
            },
        }
        body = json.dumps(payload_dict).encode("utf-8")
        sig = hmac.new(b"test_secret_123", body, hashlib.sha256).hexdigest()

        response = self.client.post(
            "/api/ota/channex/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_CHANNEX_SIGNATURE=sig,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "acknowledged")
        self.assertTrue(data["result"]["success"])

    def test_webhook_post_rejected_with_invalid_signature(self):
        body = b'{"event": "test"}'
        response = self.client.post(
            "/api/ota/channex/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_CHANNEX_SIGNATURE="invalid_signature_hash",
        )
        self.assertEqual(response.status_code, 403)
