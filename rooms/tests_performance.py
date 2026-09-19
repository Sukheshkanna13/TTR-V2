import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from payments.models import Payment, ProcessedWebhookEvent
from rooms.models import Booking, Property, Room, RoomImage, RoomRate
from superadmin.models import PropertyTaxConfig

User = get_user_model()


class BackendPerformanceAndEagerLoadingTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.prop = Property.objects.create(name="Bengaluru Heritage", city="Bengaluru", address="MG Road", is_active=True)

        # Create 5 rooms each with an image and a dynamic rate
        self.rooms = []
        for i in range(5):
            room = Room.objects.create(
                property=self.prop,
                name=f"Room {i+1}",
                city="Bengaluru",
                room_type="deluxe",
                price_per_night=Decimal("3500.00"),
                capacity=2,
                is_active=True,
                operational_status="available",
            )
            RoomImage.objects.create(room=room, caption=f"Photo {i+1}", order=0, is_primary=True)
            RoomRate.objects.create(
                room=room,
                start_date=timezone.now().date(),
                end_date=timezone.now().date() + timedelta(days=30),
                price=Decimal("3800.00"),
            )
            self.rooms.append(room)

    def test_search_rooms_query_count_is_bounded(self):
        """
        Verify that room search does NOT suffer from N+1 queries.
        For 5 rooms, unoptimized code issued 1 (rooms) + 5 (prop) + 5 (img) + 5 (rates) = 16+ queries.
        With select_related and prefetch_related, query count remains small and constant (O(1)).
        """
        today = timezone.now().date()
        ci = (today + timedelta(days=5)).isoformat()
        co = (today + timedelta(days=7)).isoformat()

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                f"/rooms/search/?city=Bengaluru&check_in={ci}&check_out={co}&guests=2",
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["rooms"]), 5)

        # Verify query count is bounded (under 7 queries including DRF auth/session/checks)
        self.assertLessEqual(len(ctx.captured_queries), 7, f"Captured too many queries: {len(ctx.captured_queries)}")

    def test_tax_config_caching_and_invalidation(self):
        """
        Verify that PropertyTaxConfig is cached and invalidated on save.
        """
        tax_cfg = PropertyTaxConfig.objects.create(
            property=self.prop,
            threshold=Decimal("7500.00"),
            low_rate_pct=Decimal("12.00"),
            high_rate_pct=Decimal("18.00"),
        )

        user = User.objects.create_user(email="taxguest@example.com", phone="9999999999", full_name="Tax Guest")
        today = timezone.now().date()
        booking = Booking.objects.create(
            room=self.rooms[0],
            user=user,
            check_in=today + timedelta(days=1),
            check_out=today + timedelta(days=3),
            guests=2,
            total_price=Decimal("6000.00"),
            status="confirmed",
        )

        # First compute_tax computes and caches
        tax_amount1 = booking.compute_tax()
        self.assertEqual(tax_amount1, Decimal("720.00"))  # 12% of 6000

        # Verify cache key exists
        cache_key = f"ttr_tax_config_prop_{self.prop.id}"
        self.assertIsNotNone(cache.get(cache_key))

        # Update tax config -> cache key must be deleted
        tax_cfg.low_rate_pct = Decimal("5.00")
        tax_cfg.save()
        self.assertIsNone(cache.get(cache_key))

        # Next compute_tax recalculates with updated rate
        tax_amount2 = booking.compute_tax()
        self.assertEqual(tax_amount2, Decimal("300.00"))  # 5% of 6000


@override_settings(RAZORPAY_WEBHOOK_SECRET="test_webhook_secret_xyz")
class WebhookIdempotencyTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.prop = Property.objects.create(name="Pondy Villa", city="Pondy", address="Beach", is_active=True)
        self.room = Room.objects.create(
            property=self.prop, name="Villa 1", city="Pondy", room_type="deluxe",
            price_per_night=Decimal("5000.00"), capacity=2, is_active=True,
        )
        self.user = User.objects.create_user(email="wh_user@example.com", phone="8888888888", full_name="WH User")

    def test_razorpay_webhook_replay_protection(self):
        today = timezone.now().date()
        booking = Booking.objects.create(
            room=self.room, user=self.user, check_in=today + timedelta(days=5),
            check_out=today + timedelta(days=7), guests=2, total_price=Decimal("10000.00"),
            status="pending", razorpay_order_id="order_replay_test_123",
            hold_expires_at=timezone.now() + timedelta(minutes=10),
        )
        Payment.objects.create(
            booking=booking, razorpay_order_id="order_replay_test_123",
            amount=Decimal("10000.00"), status="created",
        )

        payload = {
            "event": "payment.captured",
            "id": "evt_replay_001",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_replay_456",
                        "order_id": "order_replay_test_123",
                        "amount": 1000000,
                        "status": "captured",
                    }
                }
            }
        }
        body = json.dumps(payload).encode("utf-8")
        sig = hmac.new(b"test_webhook_secret_xyz", body, hashlib.sha256).hexdigest()

        # First request -> Processed
        res1 = self.client.post(
            "/payments/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["status"], "processed")

        # Verify record in ProcessedWebhookEvent
        self.assertTrue(
            ProcessedWebhookEvent.objects.filter(source="razorpay", event_id="evt_replay_001").exists()
        )

        # Second request (Replay / Retry) -> Returned immediately as already_processed
        res2 = self.client.post(
            "/payments/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=sig,
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["status"], "already_processed")
