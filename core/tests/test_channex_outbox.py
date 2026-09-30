"""
C4 — ARI outbox: record_ari_change, per-date availability, the coalescing
worker (batching, rate limit, retry/backoff) and the batched Channex client.
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.ota import tasks
from core.ota.availability import compute_per_date_availability
from core.ota.channex import ChannexAPIError, ChannexConfigError, ChannexManager
from core.ota.dispatch import record_ari_change
from core.ota.models import ARIChange, ChannexProperty, ChannexRoomType
from rooms.models import Booking, OTABlock, Property, Room

User = get_user_model()


class FakeClient:
    """Stands in for ChannexManager; records calls, optionally raises."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def push_availability_values(self, values):
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        return f"task-{len(self.calls)}"


class OutboxTestBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.prop = Property.objects.create(name="Pondy", city="Pondicherry")
        self.mapping = ChannexProperty.objects.create(property=self.prop, channex_property_id=uuid.uuid4())
        self.double_uuid = uuid.uuid4()
        self.single_uuid = uuid.uuid4()
        ChannexRoomType.objects.create(property_mapping=self.mapping, room_type="double",
                                       channex_room_type_id=self.double_uuid)
        ChannexRoomType.objects.create(property_mapping=self.mapping, room_type="single",
                                       channex_room_type_id=self.single_uuid)
        self.doubles = [self._room(f"D{i}", "double") for i in range(2)]
        self.single = self._room("S1", "single")
        self.user = User.objects.create_user(email="g@example.com", phone="9999999999", full_name="Guest")

    def _room(self, name, room_type, prop=None):
        prop = prop or self.prop
        return Room.objects.create(property=prop, name=name, city=prop.city, room_type=room_type,
                                   price_per_night=Decimal("3000"), capacity=2)

    def _book(self, room, start, nights, status="confirmed", **extra):
        return Booking.objects.create(room=room, user=self.user, check_in=start,
                                      check_out=start + timedelta(days=nights), guests=1,
                                      total_price=Decimal("3000"), status=status, **extra)

    def d(self, offset):
        return self.today + timedelta(days=offset)

    def run_outbox(self, client):
        with mock.patch.object(tasks, "_get_client", return_value=client):
            return tasks.process_ari_outbox()


class RecordARIChangeTests(OutboxTestBase):
    def test_creates_one_row_per_change_type(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(3), ("availability", "rates"))
        rows = ARIChange.objects.order_by("change_type")
        self.assertEqual([r.change_type for r in rows], ["availability", "rates"])
        self.assertTrue(all(r.status == "pending" and r.date_to == self.d(3) for r in rows))

    def test_accepts_iso_strings_and_dedupes_types(self):
        record_ari_change("double", self.prop.id, self.d(1).isoformat(), self.d(2).isoformat(),
                          ("availability", "availability"))
        self.assertEqual(ARIChange.objects.count(), 1)

    def test_noop_for_unmapped_or_inactive_property(self):
        other = Property.objects.create(name="Auro", city="Auroville")
        record_ari_change("double", other.id, self.d(1), self.d(2))
        self.mapping.is_active = False
        self.mapping.save()
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        self.assertEqual(ARIChange.objects.count(), 0)

    def test_noop_for_empty_range(self):
        record_ari_change("double", self.prop.id, self.d(2), self.d(2))
        self.assertEqual(ARIChange.objects.count(), 0)

    def test_programming_errors_raise(self):
        with self.assertRaises(ValueError):
            record_ari_change("double", self.prop.id, self.d(1), self.d(2), ("prices",))
        with self.assertRaises(ValueError):
            record_ari_change("double", self.prop.id, "not-a-date", self.d(2))


class PerDateAvailabilityTests(OutboxTestBase):
    def test_counts_each_night_independently(self):
        self._book(self.doubles[0], self.d(2), 1)                      # night d2 only
        self._book(self.doubles[1], self.d(2), 2)                      # nights d2, d3
        OTABlock.objects.create(room=self.doubles[0], start_date=self.d(4), end_date=self.d(5))
        self._book(self.doubles[1], self.d(1), 1, status="cancelled")  # ignored
        self._book(self.doubles[1], self.d(1), 1, status="pending",
                   hold_expires_at=timezone.now() - timedelta(minutes=1))  # expired hold ignored
        self._book(self.doubles[0], self.d(0), 1, status="pending",
                   hold_expires_at=timezone.now() + timedelta(minutes=5))  # live hold counts

        result = compute_per_date_availability("double", self.prop.id, self.d(0), self.d(6))
        self.assertEqual(result, {
            self.d(0).isoformat(): 1, self.d(1).isoformat(): 2, self.d(2).isoformat(): 0,
            self.d(3).isoformat(): 1, self.d(4).isoformat(): 1, self.d(5).isoformat(): 2,
        })

    def test_matches_legacy_single_night_calculation(self):
        self._book(self.doubles[0], self.d(1), 3)
        OTABlock.objects.create(room=self.doubles[1], start_date=self.d(2), end_date=self.d(4))
        result = compute_per_date_availability("double", self.prop.id, self.d(0), self.d(6))
        for offset in range(6):
            legacy = ChannexManager.calculate_available_count(
                "double", self.d(offset), self.d(offset + 1), property_id=self.prop.id)
            self.assertEqual(result[self.d(offset).isoformat()], legacy, offset)

    def test_isolated_per_property(self):
        other = Property.objects.create(name="Auro", city="Auroville")
        self._room("X", "double", prop=other)
        result = compute_per_date_availability("double", self.prop.id, self.d(0), self.d(1))
        self.assertEqual(result[self.d(0).isoformat()], 2)


class OutboxWorkerTests(OutboxTestBase):
    def test_coalesces_property_changes_into_one_call(self):
        self._book(self.doubles[0], self.d(2), 1)
        record_ari_change("double", self.prop.id, self.d(1), self.d(3))
        record_ari_change("double", self.prop.id, self.d(2), self.d(4))   # overlaps
        record_ari_change("double", self.prop.id, self.d(4), self.d(5))   # touches
        record_ari_change("single", self.prop.id, self.d(1), self.d(2))

        client = FakeClient()
        summary = self.run_outbox(client)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(summary["calls"], 1)
        self.assertEqual(summary["sent"], 4)
        values = client.calls[0]
        prop_uuid = str(self.mapping.channex_property_id)
        self.assertCountEqual(values, [
            {"property_id": prop_uuid, "room_type_id": str(self.double_uuid),
             "date_from": self.d(1).isoformat(), "date_to": self.d(1).isoformat(), "availability": 2},
            {"property_id": prop_uuid, "room_type_id": str(self.double_uuid),
             "date_from": self.d(2).isoformat(), "date_to": self.d(2).isoformat(), "availability": 1},
            {"property_id": prop_uuid, "room_type_id": str(self.double_uuid),
             "date_from": self.d(3).isoformat(), "date_to": self.d(4).isoformat(), "availability": 2},
            {"property_id": prop_uuid, "room_type_id": str(self.single_uuid),
             "date_from": self.d(1).isoformat(), "date_to": self.d(1).isoformat(), "availability": 1},
        ])
        self.assertFalse(ARIChange.objects.exclude(status="sent").exists())
        self.assertEqual(set(ARIChange.objects.values_list("channex_task_id", flat=True)), {"task-1"})

    def test_nothing_due_means_no_calls(self):
        client = FakeClient()
        self.assertEqual(self.run_outbox(client), {"claimed": 0})
        self.assertEqual(client.calls, [])

    def test_retryable_error_backs_off_then_fails_after_max_retries(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        client = FakeClient(error=ChannexAPIError(429, "slow down"))

        before = timezone.now()
        self.run_outbox(client)
        row = ARIChange.objects.get()
        self.assertEqual((row.status, row.retry_count), ("pending", 1))
        self.assertGreaterEqual(row.next_retry_at, before + timedelta(seconds=30))
        self.assertIn("429", row.error_detail)

        # Not due yet -> not retried early.
        self.run_outbox(client)
        self.assertEqual(len(client.calls), 1)

        # Second failure doubles the backoff.
        ARIChange.objects.update(next_retry_at=timezone.now())
        before = timezone.now()
        self.run_outbox(client)
        row.refresh_from_db()
        self.assertEqual(row.retry_count, 2)
        self.assertGreaterEqual(row.next_retry_at, before + timedelta(seconds=60))

        with override_settings(CHANNEX_OUTBOX_MAX_RETRIES=2):
            ARIChange.objects.update(next_retry_at=timezone.now())
            self.run_outbox(client)
        row.refresh_from_db()
        self.assertEqual(row.status, "failed")
        self.assertIn("Gave up", row.error_detail)

    def test_retry_after_header_is_honoured(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        before = timezone.now()
        self.run_outbox(FakeClient(error=ChannexAPIError(429, "slow", retry_after=600)))
        self.assertGreaterEqual(ARIChange.objects.get().next_retry_at, before + timedelta(seconds=600))

    def test_server_and_network_errors_retry(self):
        for status in (503, 0):
            ARIChange.objects.all().delete()
            record_ari_change("double", self.prop.id, self.d(1), self.d(2))
            self.run_outbox(FakeClient(error=ChannexAPIError(status, "boom")))
            self.assertEqual(ARIChange.objects.get().status, "pending", status)

    def test_client_error_fails_immediately(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        self.run_outbox(FakeClient(error=ChannexAPIError(422, "bad room type")))
        row = ARIChange.objects.get()
        self.assertEqual((row.status, row.retry_count), ("failed", 0))

    def test_unexpected_exception_is_retried_not_dropped(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        self.run_outbox(FakeClient(error=RuntimeError("surprise")))
        row = ARIChange.objects.get()
        self.assertEqual((row.status, row.retry_count), ("pending", 1))

    def test_missing_api_key_pauses_without_spending_retries(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        summary = self.run_outbox(FakeClient(error=ChannexConfigError("no key")))
        row = ARIChange.objects.get()
        self.assertEqual((row.status, row.retry_count), ("pending", 0))
        self.assertLessEqual(row.next_retry_at, timezone.now())
        self.assertEqual(summary["paused"], 1)

    def test_call_budget_defers_remaining_properties(self):
        other = Property.objects.create(name="Auro", city="Auroville")
        other_map = ChannexProperty.objects.create(property=other, channex_property_id=uuid.uuid4())
        ChannexRoomType.objects.create(property_mapping=other_map, room_type="double",
                                       channex_room_type_id=uuid.uuid4())
        self._room("A1", "double", prop=other)
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        record_ari_change("double", other.id, self.d(1), self.d(2))

        client = FakeClient()
        with override_settings(CHANNEX_OUTBOX_MAX_CALLS_PER_RUN=1):
            summary = self.run_outbox(client)
            self.assertEqual((len(client.calls), summary["deferred"]), (1, 1))
            deferred = ARIChange.objects.get(status="pending")
            self.assertEqual((deferred.property_mapping_id, deferred.retry_count), (other_map.id, 0))
            self.assertLessEqual(deferred.next_retry_at, timezone.now())
            self.run_outbox(client)
        self.assertEqual(len(client.calls), 2)
        self.assertFalse(ARIChange.objects.exclude(status="sent").exists())

    def test_unmapped_room_type_fails_with_explanation(self):
        self._room("L1", "deluxe")
        record_ari_change("deluxe", self.prop.id, self.d(1), self.d(2))
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        client = FakeClient()
        self.run_outbox(client)
        self.assertEqual(len(client.calls), 1)
        failed = ARIChange.objects.get(status="failed")
        self.assertEqual(failed.room_type, "deluxe")
        self.assertIn("No Channex room-type mapping", failed.error_detail)

    def test_past_dates_are_skipped_not_pushed(self):
        record_ari_change("double", self.prop.id, self.d(-5), self.d(-2))
        client = FakeClient()
        self.run_outbox(client)
        self.assertEqual(client.calls, [])
        self.assertEqual(ARIChange.objects.get().status, "sent")

    def test_rates_rows_wait_for_their_builder(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2), ("rates", "restrictions"))
        client = FakeClient()
        self.run_outbox(client)
        self.assertEqual(client.calls, [])
        self.assertEqual(ARIChange.objects.filter(status="pending", retry_count=0).count(), 2)

    def test_inactive_mapping_is_not_pushed(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        self.mapping.is_active = False
        self.mapping.save()
        client = FakeClient()
        self.run_outbox(client)
        self.assertEqual(client.calls, [])
        self.assertEqual(ARIChange.objects.get().status, "pending")

    def test_leased_rows_are_not_claimed_twice(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        claimed = tasks._claim_rows(timezone.now())
        self.assertEqual(len(claimed), 1)
        self.assertEqual(tasks._claim_rows(timezone.now()), [])  # a concurrent run sees nothing
        # After the lease expires (worker crashed), the row is claimable again.
        later = timezone.now() + timedelta(seconds=tasks._cfg("LEASE_SECONDS") + 1)
        self.assertEqual(len(tasks._claim_rows(later)), 1)

    def test_rows_recorded_during_a_push_stay_pending(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        test = self

        class RecordingClient(FakeClient):
            def push_availability_values(self, values):
                record_ari_change("double", test.prop.id, test.d(1), test.d(2))
                return super().push_availability_values(values)

        self.run_outbox(RecordingClient())
        self.assertEqual(ARIChange.objects.filter(status="pending").count(), 1)
        self.assertEqual(ARIChange.objects.filter(status="sent").count(), 1)


class ChannexClientBatchTests(TestCase):
    def _response(self, status, body=None, headers=None):
        resp = mock.Mock(status_code=status, headers=headers or {}, text=str(body or ""))
        resp.content = b"x" if body is not None else b""
        resp.json.return_value = body
        return resp

    def test_posts_values_and_returns_task_id(self):
        client = ChannexManager(api_key="k", api_url="https://staging.channex.io/api/v1/")
        values = [{"property_id": "p", "room_type_id": "r", "date_from": "2026-10-01",
                   "date_to": "2026-10-01", "availability": 3}]
        with mock.patch("core.ota.channex.requests.post",
                        return_value=self._response(200, {"data": [{"id": "task-9", "type": "task"}]})) as post:
            self.assertEqual(client.push_availability_values(values), "task-9")
        url = post.call_args.args[0]
        self.assertEqual(url, "https://staging.channex.io/api/v1/availability")
        self.assertEqual(post.call_args.kwargs["json"], {"values": values})
        self.assertEqual(post.call_args.kwargs["headers"]["user-api-key"], "k")

    def test_restrictions_endpoint(self):
        client = ChannexManager(api_key="k", api_url="https://x/api/v1")
        with mock.patch("core.ota.channex.requests.post",
                        return_value=self._response(200, {"data": [{"id": "t"}]})) as post:
            client.push_restriction_values([{"rate_plan_id": "r"}])
        self.assertEqual(post.call_args.args[0], "https://x/api/v1/restrictions")

    def test_error_classification(self):
        client = ChannexManager(api_key="k", api_url="https://x")
        cases = [(429, True, {"Retry-After": "30"}), (500, True, {}), (422, False, {}), (401, False, {})]
        for status, retryable, headers in cases:
            with mock.patch("core.ota.channex.requests.post",
                            return_value=self._response(status, {"errors": "x"}, headers)):
                with self.assertRaises(ChannexAPIError) as ctx:
                    client.push_availability_values([{"a": 1}])
            self.assertEqual((ctx.exception.status_code, ctx.exception.retryable), (status, retryable))
        self.assertEqual(ctx.exception.retry_after, None)

    def test_retry_after_parsed(self):
        client = ChannexManager(api_key="k", api_url="https://x")
        with mock.patch("core.ota.channex.requests.post",
                        return_value=self._response(429, {}, {"Retry-After": "45"})):
            with self.assertRaises(ChannexAPIError) as ctx:
                client.push_availability_values([{"a": 1}])
        self.assertEqual(ctx.exception.retry_after, 45)

    def test_network_error_is_retryable(self):
        client = ChannexManager(api_key="k", api_url="https://x")
        with mock.patch("core.ota.channex.requests.post", side_effect=requests.Timeout("slow")):
            with self.assertRaises(ChannexAPIError) as ctx:
                client.push_availability_values([{"a": 1}])
        self.assertTrue(ctx.exception.retryable)

    @override_settings(CHANNEX_API_KEY="")
    def test_missing_key_raises_config_error_never_fakes_success(self):
        with mock.patch("core.ota.channex.requests.post") as post:
            with self.assertRaises(ChannexConfigError):
                ChannexManager(api_key="").push_availability_values([{"a": 1}])
        post.assert_not_called()


class ARIChangeAdminTests(OutboxTestBase):
    def test_requeue_action_resets_failed_rows(self):
        record_ari_change("double", self.prop.id, self.d(1), self.d(2))
        ARIChange.objects.update(status="failed", retry_count=5, error_detail="x")
        admin_user = User.objects.create_superuser(email="a@example.com", password="pw-12345!", full_name="A")
        self.client.force_login(admin_user)
        row = ARIChange.objects.get()
        resp = self.client.post(reverse("admin:core_arichange_changelist"),
                                {"action": "requeue_changes", "_selected_action": [str(row.pk)]})
        self.assertEqual(resp.status_code, 302)
        row.refresh_from_db()
        self.assertEqual((row.status, row.retry_count, row.error_detail), ("pending", 0, ""))
