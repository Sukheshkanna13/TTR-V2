import logging
import secrets
from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from django_q.tasks import async_task

from accounts.models import UserProfile
from payments.models import Payment
from rooms.models import Booking, Room, OTABlock

User = get_user_model()
logger = logging.getLogger(__name__)


def create_walk_in_booking(
    room: Room,
    check_in: date,
    check_out: date,
    guests: int,
    guest_name: str,
    guest_phone: str,
    guest_email: str = "",
    guest_id_type: str = "",
    guest_id_number: str = "",
    payment_method: str = Payment.METHOD_CASH,
    price_override: Decimal = None,
    created_by_staff = None,
    operational_notes: str = "",
) -> Booking:
    """
    Create a confirmed walk-in / in-person reservation.
    Atomically locks room, assigns or auto-creates guest user account,
    creates Payment record, computes tax, and dispatches receipts.
    """
    if check_out <= check_in:
        raise ValueError("Check-out date must be after check-in date.")

    # 1. Check availability with row lock on Room
    with transaction.atomic():
        locked_room = Room.objects.select_for_update().get(pk=room.pk)

        # Check existing confirmed / non-expired holds
        overlapping_bookings = Booking.objects.filter(
            room=locked_room,
            check_in__lt=check_out,
            check_out__gt=check_in,
            status__in=["confirmed", "pending"],
        )
        for b in overlapping_bookings:
            if b.status == "confirmed" or (b.status == "pending" and b.hold_expires_at and b.hold_expires_at > timezone.now()):
                raise ValueError(f"Room {locked_room.name} is already booked for these dates.")

        # Check OTA blocks
        if OTABlock.objects.filter(room=locked_room, start_date__lt=check_out, end_date__gt=check_in).exists():
            raise ValueError(f"Room {locked_room.name} has an active block during these dates.")

        # 2. Resolve or create guest user account
        clean_email = (guest_email or "").strip().lower()
        clean_phone = (guest_phone or "").strip()
        user = None

        if clean_email:
            user = User.objects.filter(email=clean_email).first()

        if not user and clean_phone:
            # Check by phone
            user = User.objects.filter(phone=clean_phone).first()

        if not user:
            # Auto-generate a guest user so they can log in via OTP
            phone_digits = ''.join(c for c in clean_phone if c.isdigit())
            fallback_email = f"guest_{phone_digits or secrets.token_hex(4)}@guest.templeandtowns.in"
            target_email = clean_email or fallback_email
            user = User.objects.create(
                email=target_email,
                full_name=guest_name.strip(),
                phone=clean_phone,
                password=make_password(secrets.token_urlsafe(16)),
                is_active=True,
            )
            UserProfile.objects.get_or_create(user=user, defaults={'role': 'guest'})

        # 3. Determine price
        if price_override is not None and price_override > Decimal('0.00'):
            total_price = Decimal(str(price_override))
        else:
            total_price = Decimal(str(locked_room.calculate_price(check_in, check_out)))

        # 4. Create confirmed booking
        booking = Booking.objects.create(
            room=locked_room,
            user=user,
            source=Booking.SOURCE_WALK_IN,
            guest_name=guest_name.strip(),
            guest_phone=clean_phone,
            guest_email=clean_email,
            guest_id_type=guest_id_type.strip(),
            guest_id_number=guest_id_number.strip(),
            created_by_staff=created_by_staff,
            operational_notes=operational_notes.strip(),
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            status="confirmed",
            total_price=total_price,
            hold_expires_at=None,
        )

        booking.generate_booking_reference()
        booking.compute_tax()

        # 5. Record Payment
        total_amount = booking.total_price + (booking.tax_amount or Decimal('0.00'))
        is_captured = payment_method != Payment.METHOD_PAY_AT_CHECKOUT
        Payment.objects.create(
            booking=booking,
            payment_method=payment_method,
            amount=total_amount,
            status="captured" if is_captured else "created",
        )

    # 6. Async side effects (outside transaction block)
    try:
        if clean_email:
            async_task(
                "payments.utils.send_invoice_email",
                str(booking.id),
                clean_email,
            )
        if clean_phone:
            async_task(
                "core.tasks.send_whatsapp_message",
                clean_phone,
                f"Your booking at {booking.room.property.name} ({booking.room.name}) is confirmed! Ref: {booking.booking_reference}",
            )
        async_task(
            "rooms.tasks.sync_ota_inventory_for_dates",
            booking.room.room_type,
            check_in.isoformat(),
            check_out.isoformat(),
            booking.room.property_id,
        )
    except Exception as e:
        logger.warning(f"Failed to enqueue walk-in booking side tasks: {e}")

    return booking


def compute_bulk_ux_signals(rooms, check_in=None, check_out=None, unavailable_ids=None):
    """
    Computes real-time scarcity, demand, and social-proof UX signals in bulk.
    Executes in O(1) database queries regardless of the number of rooms.
    Returns: dict mapping room.id -> dict of signal properties.
    """
    from datetime import timedelta
    from django.db.models import Count

    if not rooms:
        return {}

    room_list = list(rooms)
    property_ids = {r.property_id for r in room_list if r.property_id}

    # 1. Scarcity math: available rooms per (property_id, room_type)
    avail_map = {}

    if check_in and check_out and property_ids:
        if unavailable_ids is None:
            unavailable_ids = Room.objects.get_unavailable_room_ids(check_in, check_out)

        available_qs = (
            Room.objects.filter(
                property_id__in=property_ids,
                is_active=True,
                operational_status=Room.STATUS_AVAILABLE,
            )
            .exclude(id__in=unavailable_ids)
            .values("property_id", "room_type")
            .annotate(available=Count("id"))
        )
        avail_map = {(row["property_id"], row["room_type"]): row["available"] for row in available_qs}

    # 2. Demand math: bookings confirmed in last 7 days per (property_id, room_type)
    recent_map = {}
    if property_ids:
        seven_days_ago = timezone.now() - timedelta(days=7)
        recent_qs = (
            Booking.objects.filter(
                room__property_id__in=property_ids,
                created_at__gte=seven_days_ago,
                status__in=["confirmed", "completed", "pending"],
            )
            .values("room__property_id", "room__room_type")
            .annotate(recent_count=Count("id"))
        )
        recent_map = {
            (row["room__property_id"], row["room__room_type"]): row["recent_count"]
            for row in recent_qs
        }

    # 3. Assemble signals per room
    signals_by_id = {}
    for r in room_list:
        prop_id = r.property_id
        rtype = r.room_type

        # Scarcity
        remaining = None
        scarcity_badge = None
        scarcity_level = "normal"

        if check_in and check_out and prop_id:
            remaining = avail_map.get((prop_id, rtype), 0)

            if remaining == 1:
                scarcity_badge = "⚡ Only 1 room left for your dates!"
                scarcity_level = "critical"
            elif remaining == 2:
                scarcity_badge = "Hurry, only 2 rooms left!"
                scarcity_level = "warning"

        # Demand
        recent_count = recent_map.get((prop_id, rtype), 0) if prop_id else 0
        is_high_demand = recent_count >= 2
        high_demand_badge = (
            f"🔥 High Demand · Booked {recent_count} times this week"
            if is_high_demand
            else None
        )

        # Rating / Top Rated
        raw_rating = r.rating
        if raw_rating is None and hasattr(r, "property") and r.property and getattr(r.property, "rating", None):
            raw_rating = getattr(r.property, "rating", None)
        rating = float(raw_rating) if raw_rating is not None else None
        is_top_rated = rating is not None and rating >= 4.7
        top_rated_badge = f"★ Guest Favourite ({rating:.1f})" if is_top_rated else None

        signals_by_id[r.id] = {
            "remaining_count": remaining,
            "remaining_rooms": remaining,
            "scarcity_badge": scarcity_badge,
            "scarcity_level": scarcity_level,
            "is_high_demand": is_high_demand,
            "recent_bookings_count": recent_count,
            "high_demand_badge": high_demand_badge,
            "is_top_rated": is_top_rated,
            "rating": rating,
            "top_rated_badge": top_rated_badge,
            "instant_hold": True,
            "instant_hold_badge": "10-Minute Hold Guarantee",
        }

    return signals_by_id


def get_room_ux_signals(room, check_in=None, check_out=None):
    """Convenience helper to compute UX signals for a single room."""
    res = compute_bulk_ux_signals([room], check_in=check_in, check_out=check_out)
    return res.get(room.id, {})

