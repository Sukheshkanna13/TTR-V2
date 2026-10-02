"""
Channex.io Channel Manager implementation for TTR-V2.
Handles ARI (Availability, Rates, and Inventory) outbound sync and inbound webhooks.
"""

import hashlib
import hmac
import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

import requests
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.ota.base import ChannelManager

logger = logging.getLogger(__name__)


class ChannexManager(ChannelManager):
    """
    Concrete Channel Manager connector for Channex.io REST API and Webhooks.
    """

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None, webhook_secret: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "CHANNEX_API_KEY", "")
        self.api_url = (api_url or getattr(settings, "CHANNEX_API_URL", "https://api.channex.io/api/v1")).rstrip("/")
        self.webhook_secret = webhook_secret or getattr(settings, "CHANNEX_WEBHOOK_SECRET", "")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "user-api-key": self.api_key,
        }

    def verify_signature(self, payload_bytes: bytes, signature: str) -> bool:
        """
        Verify incoming webhook HMAC-SHA256 signature against CHANNEX_WEBHOOK_SECRET.
        """
        if not self.webhook_secret:
            if getattr(settings, "DEBUG", False):
                logger.warning("CHANNEX_WEBHOOK_SECRET not configured in DEBUG mode; allowing webhook.")
                return True
            logger.error("CHANNEX_WEBHOOK_SECRET not configured in production; rejecting webhook.")
            return False

        if not signature:
            return False

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        # Handle 'sha256=' prefix if present
        clean_sig = signature.replace("sha256=", "").strip()
        return hmac.compare_digest(expected, clean_sig)

    def push_inventory(
        self,
        room_type: str,
        start_date: date,
        end_date: date,
        available_count: int,
        property_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Push updated room availability count to Channex ARI endpoint.
        """
        if not self.api_key:
            logger.info(
                f"[Channex Mock] Push inventory: room_type={room_type}, {start_date}..{end_date} -> {available_count} available"
            )
            return {"success": True, "dry_run": True, "available_count": available_count}

        url = f"{self.api_url}/ari"
        payload = {
            "values": [
                {
                    "room_type_id": room_type,
                    "date_from": start_date.isoformat(),
                    "date_to": end_date.isoformat(),
                    "availability": max(0, available_count),
                }
            ]
        }
        if property_id:
            payload["values"][0]["property_id"] = str(property_id)

        try:
            resp = requests.post(url, headers=self._get_headers(), json=payload, timeout=10)
            resp.raise_for_status()
            logger.info(f"Successfully pushed inventory to Channex for {room_type} ({start_date} to {end_date}): {available_count}")
            return {"success": True, "response": resp.json() if resp.content else {}}
        except requests.RequestException as e:
            logger.error(f"Failed to push inventory to Channex: {e}")
            return {"success": False, "error": str(e)}

    def push_rates(
        self,
        room_type: str,
        start_date: date,
        end_date: date,
        rate_amount: Decimal,
        property_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Push updated pricing per night to Channex ARI endpoint.
        """
        if not self.api_key:
            logger.info(
                f"[Channex Mock] Push rate: room_type={room_type}, {start_date}..{end_date} -> Rs.{rate_amount}"
            )
            return {"success": True, "dry_run": True, "rate_amount": str(rate_amount)}

        url = f"{self.api_url}/ari"
        payload = {
            "values": [
                {
                    "room_type_id": room_type,
                    "date_from": start_date.isoformat(),
                    "date_to": end_date.isoformat(),
                    "rate": str(rate_amount),
                }
            ]
        }
        if property_id:
            payload["values"][0]["property_id"] = str(property_id)

        try:
            resp = requests.post(url, headers=self._get_headers(), json=payload, timeout=10)
            resp.raise_for_status()
            logger.info(f"Successfully pushed rate to Channex for {room_type} ({start_date} to {end_date}): Rs.{rate_amount}")
            return {"success": True, "response": resp.json() if resp.content else {}}
        except requests.RequestException as e:
            logger.error(f"Failed to push rate to Channex: {e}")
            return {"success": False, "error": str(e)}

    def handle_webhook(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delegate to processor function.
        """
        from core.ota.processor import process_channex_webhook
        return process_channex_webhook(event_type, payload)

    @staticmethod
    def calculate_available_count(room_type: str, check_in: date, check_out: date, property_id: Optional[Any] = None) -> int:
        """
        Calculate the number of rooms of `room_type` that are strictly available
        for EVERY night between check_in and check_out.
        """
        from rooms.models import Room, Booking, OTABlock

        rooms_qs = Room.objects.filter(room_type=room_type, is_active=True)
        if property_id:
            rooms_qs = rooms_qs.filter(property_id=property_id)

        total_rooms = rooms_qs.count()
        if total_rooms == 0:
            return 0

        now = timezone.now()
        booked_room_ids = Booking.objects.filter(
            room__in=rooms_qs,
            check_in__lt=check_out,
            check_out__gt=check_in,
        ).filter(
            Q(status="confirmed") | Q(status="pending", hold_expires_at__gt=now)
        ).values_list("room_id", flat=True).distinct()

        ota_blocked_ids = OTABlock.objects.filter(
            room__in=rooms_qs,
            start_date__lt=check_out,
            end_date__gt=check_in,
        ).values_list("room_id", flat=True).distinct()

        unavailable_count = len(set(list(booked_room_ids) + list(ota_blocked_ids)))
        return max(0, total_rooms - unavailable_count)
