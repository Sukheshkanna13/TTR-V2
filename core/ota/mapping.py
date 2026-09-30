"""
Channex ID mapping resolvers.

Every outbound push and inbound booking flow resolves internal TTR identifiers
(Property PK, room_type string) into Channex UUIDs through this module.  Nothing
in application code ever hardcodes a Channex UUID — it is always looked up here.

All resolvers gracefully return ``None`` (or an empty list) when no mapping
exists.  Callers treat ``None`` as "this property is not connected to Channex"
and silently no-op.

**Error policy (F4 fix):** resolvers do NOT swallow database errors.  If the DB
is unreachable or a query fails, the exception propagates so the caller (usually
the outbox worker) can retry instead of silently dropping changes.  Only
genuinely expected "not found" paths return None.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.ota.models import ChannexProperty, ChannexRatePlan, ChannexRoomType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Property resolver
# ---------------------------------------------------------------------------

def resolve_property(property_id) -> Optional[str]:
    """Return the Channex property UUID string for a TTR Property PK.

    Returns ``None`` if the property has no active Channex mapping.
    Raises on database errors so callers can retry (not silently skip).
    """
    if property_id is None:
        return None
    mapping = (
        ChannexProperty.objects
        .filter(property_id=property_id, is_active=True)
        .only("channex_property_id")
        .first()
    )
    if mapping is None:
        return None
    return str(mapping.channex_property_id)


def resolve_property_mapping(property_id) -> Optional[ChannexProperty]:
    """Return the full ``ChannexProperty`` row, or ``None``.

    Use this when you need more than just the UUID (e.g. the currency code).
    """
    if property_id is None:
        return None
    return (
        ChannexProperty.objects
        .select_related("property")
        .filter(property_id=property_id, is_active=True)
        .first()
    )


# ---------------------------------------------------------------------------
# Room-type resolver
# ---------------------------------------------------------------------------

def resolve_room_type(property_id, room_type: str) -> Optional[str]:
    """Return the Channex room-type UUID string, or ``None`` if unmapped.

    ``room_type`` is the internal string value (``"single"`` / ``"double"`` /
    ``"deluxe"``).
    """
    if property_id is None or not room_type:
        return None
    mapping = (
        ChannexRoomType.objects
        .filter(
            property_mapping__property_id=property_id,
            property_mapping__is_active=True,
            room_type=room_type,
        )
        .only("channex_room_type_id")
        .first()
    )
    if mapping is None:
        return None
    return str(mapping.channex_room_type_id)


# ---------------------------------------------------------------------------
# Rate-plan resolvers
# ---------------------------------------------------------------------------

def resolve_rate_plans(property_id, room_type: str) -> list[ChannexRatePlan]:
    """Return all Channex rate-plan mappings for a room type at a property.

    Returns an empty list if no mappings exist.  The caller can iterate these
    to push rates/restrictions per rate plan (some room types carry multiple
    plans — e.g. BAR + B&B).
    """
    if property_id is None or not room_type:
        return []
    return list(
        ChannexRatePlan.objects
        .filter(
            room_type_mapping__property_mapping__property_id=property_id,
            room_type_mapping__property_mapping__is_active=True,
            room_type_mapping__room_type=room_type,
        )
        .select_related("room_type_mapping", "room_type_mapping__property_mapping")
        # Deterministic order: default plan first, then by creation time.
        .order_by("-is_default", "created_at")
    )


def resolve_default_rate_plan(
    property_id, room_type: str,
) -> Optional[ChannexRatePlan]:
    """Return the default (``is_default=True``) rate plan, or ``None``.

    The schema enforces at most one default per room type via a conditional
    unique constraint, so this always returns 0 or 1 row.
    """
    if property_id is None or not room_type:
        return None
    return (
        ChannexRatePlan.objects
        .filter(
            room_type_mapping__property_mapping__property_id=property_id,
            room_type_mapping__property_mapping__is_active=True,
            room_type_mapping__room_type=room_type,
            is_default=True,
        )
        .select_related("room_type_mapping", "room_type_mapping__property_mapping")
        .first()
    )
