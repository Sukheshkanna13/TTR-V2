"""
OTA (Online Travel Agency) Channel Manager integration package for TTR-V2.
Supports 2-way synchronization with Channex for Booking.com, Agoda, MakeMyTrip, etc.
"""

from .base import ChannelManager
from .channex import ChannexManager
from .processor import process_channex_webhook

__all__ = ["ChannelManager", "ChannexManager", "process_channex_webhook"]
