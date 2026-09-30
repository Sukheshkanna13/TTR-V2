"""
Per-date availability for Channex (fixes F7).

Channex needs one availability number per room type per night. The legacy
``ChannexManager.calculate_available_count`` returns a single number for a
whole range (rooms free on *every* night), which is wrong when nights differ.

``compute_per_date_availability`` answers the same question night by night
with exactly the same rules as ``calculate_available_count`` for a one-night
range, but in three queries total instead of three per night:

* rooms counted: ``is_active=True`` rooms of that type at that property
  (operational_status is ignored, matching search/legacy behaviour — team
  decision D4 is still open; change it here if the team decides otherwise)
* a room is unavailable on night ``d`` if it has a CONFIRMED booking, or a
  PENDING hold that has not expired yet, or an OTABlock, covering
  ``start <= d < end`` (check-out / block end are exclusive).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone


def _nights(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def compute_per_date_availability(
    room_type: str, property_id, start: date, end: date,
) -> dict[str, int]:
    """Return ``{"YYYY-MM-DD": available_count}`` for every night in [start, end)."""
    from rooms.models import Booking, OTABlock, Room

    if end <= start:
        return {}

    room_ids = set(
        Room.objects.filter(
            room_type=room_type, is_active=True, property_id=property_id,
        ).values_list("id", flat=True)
    )
    total = len(room_ids)
    if total == 0:
        return {night.isoformat(): 0 for night in _nights(start, end)}

    now = timezone.now()
    busy: dict[date, set] = defaultdict(set)

    bookings = (
        Booking.objects.filter(room_id__in=room_ids, check_in__lt=end, check_out__gt=start)
        .filter(Q(status="confirmed") | Q(status="pending", hold_expires_at__gt=now))
        .values_list("room_id", "check_in", "check_out")
    )
    blocks = OTABlock.objects.filter(
        room_id__in=room_ids, start_date__lt=end, end_date__gt=start,
    ).values_list("room_id", "start_date", "end_date")

    for source in (bookings, blocks):
        for room_id, occ_start, occ_end in source:
            for night in _nights(max(occ_start, start), min(occ_end, end)):
                busy[night].add(room_id)

    return {
        night.isoformat(): max(0, total - len(busy.get(night, ())))
        for night in _nights(start, end)
    }
