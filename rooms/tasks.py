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
