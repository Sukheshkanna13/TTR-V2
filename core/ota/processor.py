"""
Processor for inbound OTA webhooks (Channex.io).
Handles booking creation, date modifications (with smart room reallocation), and cancellations.
"""

import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from payments.models import Payment
from rooms.models import Booking, Room

logger = logging.getLogger(__name__)
User = get_user_model()


def _parse_iso_date(val: Any) -> Optional[date]:
    if isinstance(val, date):
        return val
    if not val:
        return None
    try:
        return parse_date(str(val).split("T")[0])
    except Exception:
        return None


def _resolve_ota_source(channel_name: str) -> str:
    name_lower = (channel_name or "").lower()
    if "booking.com" in name_lower or "booking" in name_lower:
        return Booking.SOURCE_OTA_BOOKING_COM
    if "agoda" in name_lower:
        return Booking.SOURCE_OTA_AGODA
    if "makemytrip" in name_lower or "mmt" in name_lower:
        return Booking.SOURCE_OTA_MAKEMYTRIP
    if "airbnb" in name_lower:
        return Booking.SOURCE_OTA_AIRBNB
    return Booking.SOURCE_OTA_OTHER


def _get_or_create_guest(customer_data: Dict[str, Any]) -> Tuple[Any, bool]:
    email = (customer_data.get("email") or "").strip().lower()
    name = (customer_data.get("name") or "OTA Guest").strip()
    phone = (customer_data.get("phone") or "0000000000").strip()

    if not email:
        email = f"ota_guest_{timezone.now().strftime('%Y%m%d%H%M%S')}@templeandtowns.in"

    user = User.objects.filter(email=email).first()
    created = False
    if not user:
        user = User.objects.create_user(
            email=email,
            full_name=name,
            phone=phone if phone else "0000000000",
            is_active=True,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])
        created = True
    elif not user.phone and phone:
        user.phone = phone
        user.save(update_fields=["phone"])

    return user, created


def _find_available_room(
    room_type: str,
    check_in: date,
    check_out: date,
    property_id: Optional[Any] = None,
    exclude_booking_id: Optional[Any] = None,
) -> Optional[Room]:
    """
    Find a room of `room_type` that has no overlapping confirmed bookings or active holds.
    """
    from django.db.models import Q

    rooms_qs = Room.objects.filter(room_type=room_type, is_active=True)
    if property_id:
        rooms_qs = rooms_qs.filter(property_id=property_id)

    now = timezone.now()
    bookings_qs = Booking.objects.filter(
        room__in=rooms_qs,
        check_in__lt=check_out,
        check_out__gt=check_in,
    ).filter(
        Q(status="confirmed") | Q(status="pending", hold_expires_at__gt=now)
    )

    if exclude_booking_id:
        bookings_qs = bookings_qs.exclude(pk=exclude_booking_id)

    busy_room_ids = set(bookings_qs.values_list("room_id", flat=True))

    for room in rooms_qs:
        if room.id not in busy_room_ids:
            return room

    return None


def process_channex_webhook(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatches inbound Channex webhook events.
    Supports booking.created, booking.modified, booking.cancelled.
    """
    # Normalize event name
    event = (event_type or payload.get("event") or "").lower()
    booking_data = payload.get("booking") or payload.get("data", {})

    logger.info(f"Processing Channex webhook event: {event}")

    if event in ("booking.created", "booking.new", "booking_created"):
        return _handle_booking_created(booking_data)
    elif event in ("booking.modified", "booking.updated", "booking_modified"):
        return _handle_booking_modified(booking_data)
    elif event in ("booking.cancelled", "booking_cancelled"):
        return _handle_booking_cancelled(booking_data)
    else:
        logger.warning(f"Ignored unhandled Channex webhook event: {event}")
        return {"success": True, "action": "ignored", "event": event}


def _handle_booking_created(data: Dict[str, Any]) -> Dict[str, Any]:
    ota_id = str(data.get("id") or data.get("ota_reservation_code") or "").strip()
    if not ota_id:
        return {"success": False, "error": "Missing reservation id in payload"}

    # Idempotency check
    existing = Booking.objects.filter(ota_reservation_id=ota_id).first()
    if existing:
        logger.info(f"Channex booking {ota_id} already exists (Booking ID: {existing.id})")
        return {"success": True, "action": "already_exists", "booking_id": str(existing.id)}

    check_in = _parse_iso_date(data.get("check_in") or data.get("arrival_date"))
    check_out = _parse_iso_date(data.get("check_out") or data.get("departure_date"))

    if not check_in or not check_out or check_out <= check_in:
        return {"success": False, "error": f"Invalid check_in/check_out dates: {check_in} to {check_out}"}

    room_type = (data.get("room_type") or data.get("room_type_id") or "deluxe").lower()
    property_id = data.get("property_id")
    customer_data = data.get("customer") or {}
    channel_name = data.get("channel") or data.get("ota_name") or "OTA"
    total_price = Decimal(str(data.get("total_price") or data.get("amount") or "0.00"))
    guests = int(data.get("guests") or data.get("occupancy") or 2)
    notes = data.get("notes") or ""

    with transaction.atomic():
        guest_user, _ = _get_or_create_guest(customer_data)
        source = _resolve_ota_source(channel_name)

        # Find room
        room = _find_available_room(room_type, check_in, check_out, property_id=property_id)
        operational_notes = f"Booked via {channel_name} (OTA Ref: {ota_id})."
        if notes:
            operational_notes += f" Guest Notes: {notes}"

        if not room:
            # Try any available room
            room = Room.objects.filter(is_active=True).first()
            operational_notes += f"\n[OVERBOOKING WARNING] No available room of type '{room_type}' found at arrival. Front desk review required."

        if not room:
            return {"success": False, "error": "No rooms configured in database"}

        booking = Booking.objects.create(
            room=room,
            user=guest_user,
            source=source,
            guest_name=customer_data.get("name") or guest_user.full_name or "OTA Guest",
            guest_phone=customer_data.get("phone") or guest_user.phone,
            guest_email=customer_data.get("email") or guest_user.email,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            status="confirmed",
            total_price=total_price,
            tax_amount=Decimal("0.00"),
            ota_reservation_id=ota_id,
            operational_notes=operational_notes,
        )
        booking.generate_booking_reference()
        try:
            booking.compute_tax()
        except Exception:
            pass

        # Create payment record
        Payment.objects.create(
            booking=booking,
            razorpay_payment_id=f"OTA-{ota_id}",
            payment_method=Payment.METHOD_CARD_POS,  # Record as OTA settled
            amount=total_price,
            status="captured",
        )

    logger.info(f"Created OTA booking {booking.booking_reference} for {guest_user.email} (OTA ID: {ota_id})")

    # Outbound inventory update
    _enqueue_inventory_sync(room.room_type, check_in, check_out)

    return {
        "success": True,
        "action": "created",
        "booking_id": str(booking.id),
        "booking_reference": booking.booking_reference,
    }


def _handle_booking_modified(data: Dict[str, Any]) -> Dict[str, Any]:
    ota_id = str(data.get("id") or data.get("ota_reservation_code") or "").strip()
    if not ota_id:
        return {"success": False, "error": "Missing reservation id in payload"}

    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(ota_reservation_id=ota_id).first()
        if not booking:
            logger.warning(f"OTA booking {ota_id} not found for modification; creating anew.")
            return _handle_booking_created(data)

        old_ci = booking.check_in
        old_co = booking.check_out
        new_ci = _parse_iso_date(data.get("check_in") or data.get("arrival_date")) or old_ci
        new_co = _parse_iso_date(data.get("check_out") or data.get("departure_date")) or old_co

        if new_co <= new_ci:
            return {"success": False, "error": f"Invalid modified dates: {new_ci} to {new_co}"}

        dates_changed = (old_ci != new_ci or old_co != new_co)
        room_reallocated = False
        old_room_name = booking.room.name

        if dates_changed:
            # Check if current room is free on new dates
            conflicts = Booking.objects.filter(
                room=booking.room,
                check_in__lt=new_co,
                check_out__gt=new_ci,
                status="confirmed",
            ).exclude(pk=booking.pk)

            if conflicts.exists():
                # Reallocate to another vacant room of the same type
                alt_room = _find_available_room(
                    room_type=booking.room.room_type,
                    check_in=new_ci,
                    check_out=new_co,
                    property_id=booking.room.property_id,
                    exclude_booking_id=booking.pk,
                )
                if alt_room:
                    booking.room = alt_room
                    room_reallocated = True
                    booking.operational_notes += (
                        f"\n[OTA DATE MODIFICATION] Shifted from {old_ci}..{old_co} to {new_ci}..{new_co}. "
                        f"Room reallocated from {old_room_name} to {alt_room.name}."
                    )
                else:
                    booking.operational_notes += (
                        f"\n[CRITICAL OVERBOOKING NOTICE] OTA shifted dates to {new_ci}..{new_co}, "
                        f"but no vacant room of type {booking.room.room_type} exists! Staff intervention required."
                    )
            else:
                booking.operational_notes += f"\n[OTA DATE MODIFICATION] Dates updated from {old_ci}..{old_co} to {new_ci}..{new_co}."

            booking.check_in = new_ci
            booking.check_out = new_co

        # Price update if provided
        if data.get("total_price") or data.get("amount"):
            new_price = Decimal(str(data.get("total_price") or data.get("amount")))
            booking.total_price = new_price

        booking.save()

    logger.info(f"Modified OTA booking {booking.booking_reference} (Dates: {new_ci}..{new_co}, Reallocated: {room_reallocated})")

    # Outbound inventory update for old and new ranges
    if dates_changed:
        _enqueue_inventory_sync(booking.room.room_type, old_ci, old_co)
        _enqueue_inventory_sync(booking.room.room_type, new_ci, new_co)

    return {
        "success": True,
        "action": "modified",
        "booking_id": str(booking.id),
        "dates_changed": dates_changed,
        "room_reallocated": room_reallocated,
    }


def _handle_booking_cancelled(data: Dict[str, Any]) -> Dict[str, Any]:
    ota_id = str(data.get("id") or data.get("ota_reservation_code") or "").strip()
    if not ota_id:
        return {"success": False, "error": "Missing reservation id in payload"}

    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(ota_reservation_id=ota_id).first()
        if not booking:
            logger.warning(f"OTA booking {ota_id} not found for cancellation.")
            return {"success": True, "action": "not_found", "ota_id": ota_id}

        if booking.status == "cancelled":
            return {"success": True, "action": "already_cancelled", "booking_id": str(booking.id)}

        booking.status = "cancelled"
        booking.operational_notes += f"\n[OTA CANCELLATION] Cancelled via OTA channel at {timezone.now().isoformat()}."
        booking.save(update_fields=["status", "operational_notes"])

    logger.info(f"Cancelled OTA booking {booking.booking_reference} (OTA ID: {ota_id})")

    # Restore inventory on OTA channels
    _enqueue_inventory_sync(booking.room.room_type, booking.check_in, booking.check_out)

    return {"success": True, "action": "cancelled", "booking_id": str(booking.id)}


def _enqueue_inventory_sync(room_type: str, check_in: date, check_out: date):
    """
    Queue background task for outbound inventory update.
    """
    try:
        from django_q.tasks import async_task
        async_task(
            "rooms.tasks.sync_ota_inventory_for_dates",
            room_type,
            check_in.isoformat(),
            check_out.isoformat(),
        )
    except Exception as e:
        logger.warning(f"Could not enqueue async inventory sync (running synchronously if possible): {e}")
        try:
            from rooms.tasks import sync_ota_inventory_for_dates
            sync_ota_inventory_for_dates(room_type, check_in.isoformat(), check_out.isoformat())
        except Exception as sync_err:
            logger.error(f"Synchronous inventory sync failed: {sync_err}")
