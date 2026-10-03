import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Booking

logger = logging.getLogger(__name__)

def release_expired_holds():
    """
    Scheduled task to bulk update expired holds.
    Updates all PENDING bookings where hold_expires_at is in the past to EXPIRED
    and returns any coupon reserved on them to "active".

    A bulk queryset .update() bypasses Booking.expire_if_needed(), so the coupon
    release must happen here explicitly. Row locks stop a concurrent payment
    confirmation (which also locks the booking) from interleaving.

    C7.1: snapshot room_type / property_id / dates BEFORE the bulk UPDATE,
    because .update() returns only a count — no Python objects are hydrated,
    so room info is unreachable after the call. After updating, record an
    availability change for each freed date range so the outbox worker pushes
    the corrected inventory to Channex.
    """
    from core.ota.dispatch import record_ari_change
    from loyalty.models import Coupon

    now = timezone.now()
    expiring = []
    with transaction.atomic():
        expiring = list(
            Booking.objects.select_for_update()
            .filter(status="pending", hold_expires_at__lt=now)
            .values("pk", "room__room_type", "room__property_id", "check_in", "check_out")
        )
        if expiring:
            expired_ids = [row["pk"] for row in expiring]
            Coupon.objects.filter(
                status=Coupon.STATUS_APPLIED, bookings__pk__in=expired_ids
            ).update(status=Coupon.STATUS_ACTIVE)
            expired_count = Booking.objects.filter(pk__in=expired_ids).update(status="expired")
        else:
            expired_count = 0

        # Self-heal: a coupon can only be "applied" while a live hold references it.
        # Repairs coupons stranded by earlier sweeps that skipped the release.
        Coupon.objects.filter(status=Coupon.STATUS_APPLIED).exclude(
            bookings__status="pending"
        ).update(status=Coupon.STATUS_ACTIVE)

    if expired_count > 0:
        logger.info(f"Released {expired_count} expired holds.")
        for row in expiring:
            record_ari_change(
                room_type=row["room__room_type"],
                property_id=row["room__property_id"],
                date_from=row["check_in"],
                date_to=row["check_out"],
                change_types=("availability",),
            )

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
    Record an availability change in the ARI outbox for the given room_type
    and date range.  The outbox worker (core.ota.tasks.process_ari_outbox)
    coalesces pending rows, builds the per-date payload, and pushes to Channex
    with rate-limiting and retry/backoff.

    Signature kept identical to the old direct-push version so all existing
    callers (payments/services.py, rooms/services.py, core/ota/processor.py)
    continue to work without any changes.

    C6 change: replaced the direct ChannexManager.push_inventory() call (which
    used the wrong /ari endpoint and swallowed errors) with record_ari_change().
    """
    from django.utils.dateparse import parse_date
    from core.ota.dispatch import record_ari_change

    ci = parse_date(check_in_str) if isinstance(check_in_str, str) else check_in_str
    co = parse_date(check_out_str) if isinstance(check_out_str, str) else check_out_str

    if not ci or not co:
        logger.warning(
            "sync_ota_inventory_for_dates: invalid dates %r to %r — skipped",
            check_in_str, check_out_str,
        )
        return False

    # record_ari_change is a no-op when the property has no active Channex
    # mapping, so property_id=None is safe here.
    record_ari_change(
        room_type=room_type,
        property_id=property_id,
        date_from=ci,
        date_to=co,          # check_out is already the exclusive end date
        change_types=("availability",),
    )
    return True
