"""
HTTP Webhook views for OTA Channel Manager integrations.
"""

import json
import logging

from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from core.ota.channex import ChannexManager
from core.ota.processor import process_channex_webhook

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class ChannexWebhookView(View):
    """
    Receives inbound webhooks from Channex.io (Booking.com, Agoda, Airbnb, etc.).
    """

    def post(self, request, *args, **kwargs):
        signature = request.headers.get("X-Channex-Signature") or request.META.get("HTTP_X_CHANNEX_SIGNATURE", "")
        manager = ChannexManager()

        if not manager.verify_signature(request.body, signature):
            logger.warning("Rejected Channex webhook with invalid or missing signature.")
            return JsonResponse({"error": "Invalid signature"}, status=403)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            logger.error(f"Malformed JSON in Channex webhook: {e}")
            return HttpResponseBadRequest("Malformed JSON payload")

        event_type = payload.get("event") or request.headers.get("X-Channex-Event") or ""

        # Webhook idempotency and replay protection
        from payments.models import ProcessedWebhookEvent
        booking_data = payload.get("booking") or payload.get("data", {})
        ota_id = str(booking_data.get("id") or booking_data.get("ota_reservation_code") or "").strip()
        event_id = payload.get("event_id") or payload.get("id") or (f"{event_type}_{ota_id}" if ota_id else "")

        if event_id and ProcessedWebhookEvent.objects.filter(source="channex", event_id=event_id).exists():
            logger.info("Ignoring duplicate Channex webhook event %s", event_id)
            return JsonResponse({"status": "acknowledged", "already_processed": True}, status=200)

        result = process_channex_webhook(event_type, payload)

        if event_id and result.get("success"):
            ProcessedWebhookEvent.objects.get_or_create(source="channex", event_id=event_id)

        return JsonResponse({"status": "acknowledged", "result": result}, status=200)
