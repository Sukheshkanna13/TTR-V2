"""
HTTP Webhook views for OTA Channel Manager integrations.
"""

import json
import logging

from django.http import JsonResponse, HttpResponseBadRequest
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from core.ota.channex import ChannexManager, ChannexAPIError, ChannexConfigError
from core.ota.processor import process_channex_webhook

logger = logging.getLogger(__name__)

# Channex revision status → event name that process_channex_webhook understands
_STATUS_TO_EVENT = {
    "new": "booking.new",
    "modified": "booking.modified",
    "cancelled": "booking.cancelled",
}


@method_decorator(csrf_exempt, name="dispatch")
class ChannexWebhookView(View):
    """
    Receives inbound webhooks from Channex.io.

    Channex sends a notification with a booking_revision_id; we:
      1. Verify the HMAC signature.
      2. Fetch the full revision from GET /booking_revisions/:id.
      3. Deduplicate via ProcessedWebhookEvent.
      4. Process (create / modify / cancel booking).
      5. ACK via POST /booking_revisions/:id/ack so Channex stops retrying.
    """

    def post(self, request, *args, **kwargs):
        manager = ChannexManager()
        signature = request.headers.get("X-Channex-Signature") or request.META.get("HTTP_X_CHANNEX_SIGNATURE", "")

        if not manager.verify_signature(request.body, signature):
            logger.warning("Rejected Channex webhook: invalid or missing signature.")
            return JsonResponse({"error": "Invalid signature"}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            logger.error("Malformed JSON in Channex webhook: %s", exc)
            return HttpResponseBadRequest("Malformed JSON payload")

        # Channex puts the revision id at payload.booking_revision_id
        # or nested under payload.payload.booking_revision_id
        revision_id = (
            payload.get("booking_revision_id")
            or (payload.get("payload") or {}).get("booking_revision_id")
            or ""
        )
        revision_id = str(revision_id).strip()

        if revision_id:
            # ── Proper Channex flow: fetch full revision ──────────────────────
            try:
                revision = manager.fetch_booking_revision(revision_id)
            except (ChannexConfigError, ChannexAPIError) as exc:
                logger.error("Failed to fetch booking revision %s: %s", revision_id, exc)
                # Return 500 so Channex will retry delivery
                return JsonResponse({"error": "Failed to fetch revision"}, status=500)

            revision_status = str(revision.get("status") or "new").lower()
            event_type = _STATUS_TO_EVENT.get(revision_status, "booking.new")
            booking_data = revision.get("booking") or {}
            process_payload = {"event": event_type, "booking": booking_data}
            event_id = f"rev_{revision_id}"
        else:
            # ── Fallback: booking data inline (older webhook format) ──────────
            event_type = payload.get("event") or request.headers.get("X-Channex-Event") or ""
            process_payload = payload
            booking_data = payload.get("booking") or payload.get("data", {})
            ota_id = str(booking_data.get("id") or booking_data.get("ota_reservation_code") or "").strip()
            event_id = payload.get("event_id") or payload.get("id") or (f"{event_type}_{ota_id}" if ota_id else "")
            event_id = str(event_id)

        # ── Deduplication ─────────────────────────────────────────────────────
        from payments.models import ProcessedWebhookEvent
        if event_id and ProcessedWebhookEvent.objects.filter(source="channex", event_id=event_id).exists():
            logger.info("Duplicate Channex webhook ignored: %s", event_id)
            # Still ACK so Channex stops retrying
            if revision_id:
                manager.ack_booking_revision(revision_id)
            return JsonResponse({"status": "acknowledged", "already_processed": True}, status=200)

        # ── Process ───────────────────────────────────────────────────────────
        result = process_channex_webhook(event_type, process_payload)

        if event_id and result.get("success"):
            ProcessedWebhookEvent.objects.get_or_create(source="channex", event_id=event_id)

        # ── ACK (must happen even on partial success so Channex stops retrying)
        if revision_id:
            manager.ack_booking_revision(revision_id)

        return JsonResponse({"status": "acknowledged", "result": result}, status=200)
