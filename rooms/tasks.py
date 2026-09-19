import logging
from datetime import timedelta

from django.utils import timezone

from .models import Booking

logger = logging.getLogger(__name__)

def release_expired_holds():
    """
    Scheduled task to bulk update expired holds.
    Updates all PENDING bookings where hold_expires_at is in the past to EXPIRED.
    """
    now = timezone.now()
    expired_count = Booking.objects.filter(
        status="pending",
        hold_expires_at__lt=now
    ).update(status="expired")
    
    if expired_count > 0:
        logger.info(f"Released {expired_count} expired holds.")
    
    return expired_count

def auto_complete_bookings():
    """
    Scheduled task to mark past bookings as COMPLETED.
    Updates all CONFIRMED bookings where check_out date is before today to COMPLETED.
    """
    today = timezone.now().date()
    
    # Get all bookings that should be completed today
    bookings_to_complete = Booking.objects.filter(
        status="confirmed",
        check_out__lt=today
    )
    
    completed_count = 0
    for booking in bookings_to_complete:
        # Update room status to needs cleaning
        room = booking.room
        room.operational_status = "needs_cleaning"
        room.save(update_fields=["operational_status"])
        
        # Complete the booking
        booking.status = "completed"
        booking.save(update_fields=["status"])
        completed_count += 1
    
    if completed_count > 0:
        logger.info(f"Auto-completed {completed_count} past bookings and marked rooms for cleaning.")

    return completed_count

def award_loyalty_for_completed_stays():
    """
    Scheduled task: credit loyalty points 24h after checkout, but only for
    stays that weren't cancelled in that window.

    Eligible bookings are CONFIRMED or COMPLETED (auto_complete_bookings may
    have already flipped status by the time this runs), with check_out at
    least 24h in the past, and not yet awarded. A cancellation moves status
    to "cancelled" before this task ever sees the booking, so cancelled
    stays are naturally excluded rather than needing a separate check.
    """
    from loyalty.services import award_booking_points

    cutoff = timezone.now() - timedelta(hours=24)
    eligible = Booking.objects.filter(
        status__in=("confirmed", "completed"),
        loyalty_awarded=False,
        check_out__lte=cutoff.date(),
    )

    awarded_count = 0
    for booking in eligible:
        award_booking_points(booking.pk)
        awarded_count += 1

    if awarded_count > 0:
        logger.info(f"Awarded loyalty points for {awarded_count} completed stays.")

    return awarded_count


def sync_ota_inventory_for_dates(room_type: str, check_in_str: str, check_out_str: str, property_id=None):
    """
    Background worker task to compute remaining available inventory for room_type
    across the date range and push updates to Channex.
    """
    from django.utils.dateparse import parse_date
    from core.ota.channex import ChannexManager

    ci = parse_date(check_in_str) if isinstance(check_in_str, str) else check_in_str
    co = parse_date(check_out_str) if isinstance(check_out_str, str) else check_out_str

    if not ci or not co:
        logger.warning(f"Invalid dates for OTA inventory sync: {check_in_str} to {check_out_str}")
        return False

    manager = ChannexManager()
    avail = manager.calculate_available_count(room_type, ci, co, property_id=property_id)
    res = manager.push_inventory(room_type, ci, co, avail, property_id=property_id)
    return res.get("success", False)
