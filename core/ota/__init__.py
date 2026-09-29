"""
OTA (Online Travel Agency) Channel Manager integration package for TTR-V2.
Supports 2-way synchronization with Channex for Booking.com, Agoda, MakeMyTrip, etc.

Exports are loaded lazily (PEP 562). Eagerly importing ``channex``/``processor``
here is unsafe: ``processor`` calls ``get_user_model()`` at module level, which
raises ``AppRegistryNotReady`` if the package is imported while Django is still
loading models (which now happens, because ``core/models.py`` imports
``core.ota.models``). Submodules can still be imported directly, e.g.
``from core.ota.channex import ChannexManager``.
"""

__all__ = ["ChannelManager", "ChannexManager", "process_channex_webhook"]


def __getattr__(name):
    if name == "ChannelManager":
        from .base import ChannelManager
        return ChannelManager
    if name == "ChannexManager":
        from .channex import ChannexManager
        return ChannexManager
    if name == "process_channex_webhook":
        from .processor import process_channex_webhook
        return process_channex_webhook
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
