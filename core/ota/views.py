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
        result = process_channex_webhook(event_type, payload)

        return JsonResponse({"status": "acknowledged", "result": result}, status=200)
