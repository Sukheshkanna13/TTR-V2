"""
Base interface and abstract class for Channel Manager integrations.
"""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional


class ChannelManager(ABC):
    """
    Abstract Channel Manager contract for 2-way distribution of inventory, rates,
    and inbound reservation webhooks.
    """

    @abstractmethod
    def push_inventory(
        self,
        room_type: str,
        start_date: date,
        end_date: date,
        available_count: int,
        property_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Push room inventory count for a date range to the channel manager.
        """
        pass

    @abstractmethod
    def push_rates(
        self,
        room_type: str,
        start_date: date,
        end_date: date,
        rate_amount: Decimal,
        property_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Push updated room price/rate for a date range to the channel manager.
        """
        pass

    @abstractmethod
    def handle_webhook(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming webhook notification from the channel manager.
        """
        pass

    @abstractmethod
    def verify_signature(self, payload_bytes: bytes, signature: str) -> bool:
        """
        Verify incoming webhook signature for tamper-proofing.
        """
        pass
