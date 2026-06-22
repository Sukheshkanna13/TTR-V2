"""
API views for room search, hold, payment, and booking management.

Phase 2 endpoints:
    GET  /rooms/search/              — Search available rooms with filters

Phase 3 endpoints:
    POST /bookings/hold/             — Hold a room (creates PENDING booking)
    POST /bookings/<id>/pay/         — Process payment (PENDING → CONFIRMED)
    POST /bookings/<id>/cancel/      — Cancel a booking (CONFIRMED → CANCELLED)
    GET  /bookings/<id>/             — Get booking details & status
    GET  /bookings/my/               — List current user's bookings
"""

import logging
from datetime import datetime, time as dt_time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from accounts.permissions import IsEmployee
from rest_framework.response import Response
from rest_framework.views import APIView


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    Session auth without CSRF enforcement, so the hold-release endpoint can be
    called via navigator.sendBeacon on page unload (which cannot attach the CSRF
    header). Safe here: the action is idempotent and only releases the caller's
    own pending hold, so forging it has no security impact beyond self-griefing.
    """

    def enforce_csrf(self, request):
        return

from .models import Booking, Room, OTABlock, Property
from payments.models import Payment
from payments.utils import refund_razorpay_payment
from .serializers import (
    BookingSerializer,
    HoldRoomSerializer,
    RoomSerializer,
    SearchSerializer,
    OTABlockSerializer,
)

logger = logging.getLogger(__name__)


def get_unavailable_room_ids(check_in, check_out):
    """
    Find all room IDs that are blocked for the requested date range.

    A room is blocked if it has:
    - A CONFIRMED booking overlapping the dates, OR
    - A PENDING hold that hasn't expired yet overlapping the dates

    Overlap logic:
        existing.check_in < requested.check_out
        AND existing.check_out > requested.check_in
    """
    now = timezone.now()

    booked_ids = Booking.objects.filter(
        check_in__lt=check_out,
        check_out__gt=check_in,
    ).filter(
        # Confirmed bookings always block
        Q(status="confirmed")
        |
        # Pending holds block only if they haven't expired
        Q(status="pending", hold_expires_at__gt=now)
    ).values_list("room_id", flat=True)

    # Also get rooms blocked by OTA
    ota_blocked_ids = OTABlock.objects.filter(
        start_date__lt=check_out,
        end_date__gt=check_in,
    ).values_list("room_id", flat=True)

    return set(list(booked_ids) + list(ota_blocked_ids))


# =========================================================================
# PHASE 2: Room Search
# =========================================================================

class SearchRoomsView(APIView):
    """
    GET  /rooms/search/?check_in=&check_out=&city=&guests=   — URL-param search (homepage redirect)
    POST /rooms/search/  with FormData{check_in, check_out, city, guests, ...} + X-CSRFToken header

    Both methods share the same business logic via _handle_search().
    guests defaults to 1 when omitted or zero — never an error.
    city and property_id are both optional; omitting both returns all active rooms.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        # Form data comes as URL query params (redirect from homepage search form)
        return self._handle_search(request, request.query_params)

    def post(self, request):
        # Form data comes in request body as application/x-www-form-urlencoded or JSON.
        # CSRF token is validated automatically by Django's CSRF middleware via the
        # X-CSRFToken header that the frontend sends with every POST.
        return self._handle_search(request, request.data)

    def _handle_search(self, request, source_data):
        serializer = SearchSerializer(data=source_data)

        if not serializer.is_valid():
            # Return human-readable errors — flatten nested dicts for the frontend
            flat_errors = {}
            for field, msgs in serializer.errors.items():
                if isinstance(msgs, list):
                    flat_errors[field] = msgs[0] if msgs else "Invalid value."
                elif isinstance(msgs, dict):
                    # nested validation error (e.g. non_field_errors)
                    for k, v in msgs.items():
                        flat_errors[k] = v[0] if isinstance(v, list) else str(v)
                else:
                    flat_errors[field] = str(msgs)
            return Response(
                {"errors": flat_errors, "message": "Please fix the highlighted fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        city        = data.get("city")
        property_id = data.get("property_id")
        check_in    = data["check_in"]
        check_out   = data["check_out"]
        # guests is always at least 1 after serializer validation
        guests      = max(1, data.get("guests", 1))

        # Optional filters
        room_type = data.get("room_type")
        min_price = data.get("min_price")
        max_price = data.get("max_price")
        sort      = data.get("sort")

        # ----------------------------------------------------------------
        # SINGLE QUERY: find available rooms across requested dates
        # ----------------------------------------------------------------

        # Step 1: rooms blocked by confirmed bookings, active holds, or OTA blocks
        unavailable_ids = get_unavailable_room_ids(check_in, check_out)

        # Step 2: active, available rooms with sufficient capacity
        rooms = Room.objects.filter(
            is_active=True,
            operational_status="available",
            capacity__gte=guests,
        ).exclude(
            id__in=unavailable_ids,
        )

        # Step 3: scope to property > city > all (in that priority order)
        # We treat property_id='0' or empty as "All Properties"
        is_all_properties = not property_id or str(property_id).lower() in ["0", "all", "none", ""]
        
        if not is_all_properties:
            rooms = rooms.filter(property_id=property_id)
        elif city:
            rooms = rooms.filter(city__iexact=city)
        # else: no scope — return all cities/properties

        # Step 4: apply optional refinement filters (no extra DB round-trips)
        if room_type:
            rooms = rooms.filter(room_type=room_type)
        if min_price is not None:
            rooms = rooms.filter(price_per_night__gte=min_price)
        if max_price is not None:
            rooms = rooms.filter(price_per_night__lte=max_price)

        # Step 5: sorting
        if sort == "price_desc":
            rooms = rooms.order_by("-price_per_night")
        else:
            rooms = rooms.order_by("price_per_night")

        context = {"request": request, "check_in": check_in, "check_out": check_out}
        room_list  = RoomSerializer(rooms, many=True, context=context).data
        num_nights = (check_out - check_in).days

        location_label = city or "All locations"
        if not is_all_properties:
            try:
                prop = Property.objects.get(id=property_id)
                location_label = prop.name
            except (Property.DoesNotExist, ValueError):
                pass

        if not room_list:
            return Response(
                {
                    "message": f"No rooms available in {location_label} for those dates. Try adjusting your dates or destination.",
                    "rooms": [],
                    "search": {
                        "city": city,
                        "check_in": str(check_in),
                        "check_out": str(check_out),
                        "guests": guests,
                        "num_nights": num_nights,
                    },
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "message": f"{len(room_list)} room{'s' if len(room_list) != 1 else ''} available in {location_label}.",
                "rooms": room_list,
                "search": {
                    "city": city,
                    "check_in": str(check_in),
                    "check_out": str(check_out),
                    "guests": guests,
                    "num_nights": num_nights,
                },
            },
            status=status.HTTP_200_OK,
        )


class RoomDetailView(APIView):
    """
    GET /rooms/<room_id>/

    Returns full details for a single room.
    """

    permission_classes = [AllowAny]

    def get(self, request, room_id):
        try:
            room = Room.objects.prefetch_related("images").get(id=room_id, is_active=True)
        except Room.DoesNotExist:
            return Response(
                {"error": "Room not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"room": RoomSerializer(room, context={"request": request}).data},
            status=status.HTTP_200_OK,
        )


# =========================================================================
# PHASE 3: Room Hold & Booking
# =========================================================================

class HoldRoomView(APIView):
    """
    POST /bookings/hold/

    Hold a room for 10 minutes while user completes payment.

    1. User must be logged in
    2. Runs availability check (double-booking protection)
    3. Creates PENDING booking with hold_expires_at = now + 10 min
    4. Returns booking ID for payment page
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = HoldRoomSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        room_id = serializer.validated_data["room_id"]
        check_in = serializer.validated_data["check_in"]
        check_out = serializer.validated_data["check_out"]
        guests = serializer.validated_data["guests"]

        # Verify the room exists
        try:
            room = Room.objects.get(id=room_id, is_active=True, operational_status="available")
        except Room.DoesNotExist:
            return Response(
                {"error": "Room not found or no longer available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check capacity
        if guests > room.capacity:
            return Response(
                {"error": f"This room has a maximum capacity of {room.capacity} guests."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Calculate total price dynamically
        num_nights = (check_out - check_in).days
        total_price = room.calculate_price(check_in, check_out)

        # ----------------------------------------------------------------
        # DOUBLE-BOOKING PROTECTION
        # Atomic transaction + select_for_update to lock rows
        # ----------------------------------------------------------------
        try:
            with transaction.atomic():
                now = timezone.now()
                hold_duration = getattr(settings, 'HOLD_DURATION_MINUTES', 10)
                hold_expires_at = now + timedelta(minutes=hold_duration)

                # RECLAIM: if this guest already holds this exact room+dates
                # (e.g. they hit Back and returned), refresh and reuse that hold
                # instead of rejecting them with a 409 against their own hold.
                existing_hold = Booking.objects.select_for_update().filter(
                    room=room,
                    user=request.user,
                    status="pending",
                    check_in=check_in,
                    check_out=check_out,
                    hold_expires_at__gt=now,
                ).first()

                if existing_hold:
                    existing_hold.hold_expires_at = hold_expires_at
                    existing_hold.total_price = total_price
                    existing_hold.guests = guests
                    existing_hold.save(update_fields=["hold_expires_at", "total_price", "guests"])
                    booking = existing_hold
                else:
                    # Lock all OTHER bookings for this room that could overlap.
                    # The guest's own pending holds never block them.
                    overlapping = Booking.objects.select_for_update().filter(
                        room=room,
                        check_in__lt=check_out,
                        check_out__gt=check_in,
                    ).filter(
                        Q(status="confirmed")
                        | Q(status="pending", hold_expires_at__gt=now)
                    ).exclude(user=request.user, status="pending")

                    # Lock overlapping OTA blocks
                    overlapping_blocks = OTABlock.objects.select_for_update().filter(
                        room=room,
                        start_date__lt=check_out,
                        end_date__gt=check_in,
                    )

                    if overlapping.exists() or overlapping_blocks.exists():
                        return Response(
                            {
                                "error": "Sorry, this room was just taken for the selected dates. Please pick another room.",
                                "code": "ROOM_TAKEN",
                            },
                            status=status.HTTP_409_CONFLICT,
                        )

                    # Room is available — create PENDING hold
                    booking = Booking.objects.create(
                        room=room,
                        user=request.user,
                        check_in=check_in,
                        check_out=check_out,
                        guests=guests,
                        total_price=total_price,
                        status="pending",
                        hold_expires_at=hold_expires_at,
                    )

        except Exception as e:
            logger.error("Hold failed for user %s: %s", request.user.email, str(e))
            return Response(
                {"error": "Something went wrong. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            "Room held: %s held %s (%s to %s) — expires at %s",
            request.user.email,
            room.name,
            check_in,
            check_out,
            hold_expires_at,
        )

        # ----------------------------------------------------------------
        # IMMEDIATELY create Razorpay order — return everything the
        # frontend needs to open the payment modal in one shot.
        # ----------------------------------------------------------------
        payment_details = None
        try:
            from payments.models import Payment
            from payments.utils import create_razorpay_order

            # Reuse the existing order for a reclaimed hold of the same amount,
            # otherwise create a fresh one.
            existing_payment = Payment.objects.filter(
                booking=booking, status="created",
                amount=booking.total_price,
            ).first()

            if booking.razorpay_order_id and existing_payment:
                payment_details = {
                    "order_id": booking.razorpay_order_id,
                    "amount": int(booking.total_price * 100),  # paise
                    "currency": "INR",
                    "key_id": settings.RAZORPAY_KEY_ID,
                }
            else:
                order = create_razorpay_order(
                    amount_inr=booking.total_price,
                    booking_id=booking.id,
                )
                booking.razorpay_order_id = order["id"]
                booking.save(update_fields=["razorpay_order_id"])

                Payment.objects.create(
                    booking=booking,
                    razorpay_order_id=order["id"],
                    amount=booking.total_price,
                    status="created",
                )

                payment_details = {
                    "order_id": order["id"],
                    "amount": order["amount"],       # paise
                    "currency": order["currency"],
                    "key_id": settings.RAZORPAY_KEY_ID,
                }
        except Exception as pay_err:
            logger.error("Razorpay order creation failed for booking %s: %s", booking.id, str(pay_err))
            # Don't block the hold — frontend can call /payments/create-order/ separately

        response_data = {
            "message": f"Room held for {hold_duration} minutes. Please complete payment.",
            "booking": BookingSerializer(booking).data,
        }
        if payment_details:
            response_data["payment"] = payment_details

        return Response(response_data, status=status.HTTP_201_CREATED)


class ProcessPaymentView(APIView):
    """
    POST /bookings/<id>/pay/

    DEV/FALLBACK: Quick-confirm a booking without Razorpay.
    In production, use /payments/create-order/ + /payments/verify/ instead.

    Kept for testing purposes — lets you confirm a booking directly.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        if not settings.DEBUG:
            return Response(
                {"error": "This endpoint is only available in development mode."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Find the booking
        try:
            booking = Booking.objects.select_related("room").get(
                id=booking_id,
                user=request.user,
            )
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Only PENDING bookings can be paid for
        if booking.status != "pending":
            return Response(
                {
                    "error": f"This booking cannot be paid for. Current status: {booking.get_status_display()}.",
                    "status": booking.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if hold has expired
        if booking.expire_if_needed():
            return Response(
                {
                    "error": "Your hold has expired. Please search and book again.",
                    "code": "HOLD_EXPIRED",
                    "status": "expired",
                },
                status=status.HTTP_410_GONE,
            )

        # ----------------------------------------------------------------
        # PAYMENT SIMULATION (Dev/fallback)
        # In production, use /payments/create-order/ + /payments/verify/
        # ----------------------------------------------------------------
        booking.status = "confirmed"
        booking.hold_expires_at = None
        booking.save(update_fields=["status", "hold_expires_at"])

        # Generate booking reference
        booking.generate_booking_reference()

        logger.info(
            "Booking confirmed (dev): %s paid for %s (%s to %s) — Rs.%s — ref: %s",
            request.user.email,
            booking.room.name,
            booking.check_in,
            booking.check_out,
            booking.total_price,
            booking.booking_reference,
        )

        return Response(
            {
                "message": "Payment successful! Your booking is confirmed.",
                "booking": BookingSerializer(booking).data,
            },
            status=status.HTTP_200_OK,
        )


class CancelBookingView(APIView):
    """
    POST /bookings/<id>/cancel/

    Cancel a confirmed or pending booking.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        try:
            booking = Booking.objects.select_related("room").get(
                id=booking_id,
                user=request.user,
            )
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Only PENDING or CONFIRMED bookings can be cancelled
        if booking.status not in ("pending", "confirmed"):
            return Response(
                {
                    "error": f"This booking cannot be cancelled. Current status: {booking.get_status_display()}.",
                    "status": booking.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Process refund if confirmed
        refund_message = ""
        if booking.status == "confirmed":
            payment = Payment.objects.filter(booking=booking, status="captured").first()
            if payment and payment.razorpay_payment_id:
                refund = refund_razorpay_payment(payment.razorpay_payment_id)
                if refund:
                    payment.refund_id = refund.get("id")
                    payment.refund_status = refund.get("status")
                    payment.status = "refunded"
                    payment.save()
                    refund_message = " Refund has been initiated."
                else:
                    refund_message = " Cancellation successful, but automatic refund failed. Please contact support."

        booking.status = "cancelled"
        booking.hold_expires_at = None
        booking.save(update_fields=["status", "hold_expires_at"])

        logger.info("Booking cancelled: %s cancelled %s", request.user.email, booking.room.name)

        return Response(
            {
                "message": f"Booking cancelled successfully.{refund_message}",
                "booking": BookingSerializer(booking).data,
            },
            status=status.HTTP_200_OK,
        )


class ReleaseHoldView(APIView):
    """
    POST /bookings/<id>/release/

    Release an unpaid hold early so the room frees immediately, instead of
    blocking other guests (and the same guest) for the full 10-minute window.

    Called by the checkout page when the guest dismisses the payment modal,
    payment fails, or they navigate away / refresh / hit Back (the last three
    via navigator.sendBeacon). Idempotent and ownership-scoped, so it is safe
    to fire on unload and to call more than once.
    """

    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
        try:
            booking = Booking.objects.select_related("room").get(
                id=booking_id,
                user=request.user,
            )
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        released = booking.release_hold("abandoned")
        if released:
            logger.info("Hold released early: %s released %s", request.user.email, booking.room.name)

        return Response(
            {"message": "Hold released.", "released": released, "status": booking.status},
            status=status.HTTP_200_OK,
        )


class BookingDetailView(APIView):
    """
    GET /bookings/<id>/

    Get booking details. Auto-expires the hold if timed out.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, booking_id):
        try:
            booking = Booking.objects.select_related("room").get(
                id=booking_id,
                user=request.user,
            )
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Auto-expire if hold has timed out
        booking.expire_if_needed()

        return Response(
            {"booking": BookingSerializer(booking).data},
            status=status.HTTP_200_OK,
        )


class ConfirmationView(APIView):
    """
    GET /bookings/ref/<booking_ref>/confirmation/

    Shows booking confirmation page after successful payment.
    Accessible to the booking owner only.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, booking_ref):
        try:
            booking = Booking.objects.select_related("room", "user").get(
                booking_reference=booking_ref,
                user=request.user,
            )
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if booking.status != "confirmed":
            return Response(
                {"error": "This booking is not confirmed.", "status": booking.status},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get payment ID if available
        payment_id = None
        try:
            from payments.models import Payment
            payment = Payment.objects.filter(
                booking=booking, status="captured"
            ).first()
            if payment:
                payment_id = payment.razorpay_payment_id
        except Exception:
            pass

        return Response(
            {
                "message": "Your booking is confirmed!",
                "confirmation": {
                    "booking_reference": booking.booking_reference,
                    "room_name": booking.room.name,
                    "city": booking.room.city,
                    "room_type": booking.room.get_room_type_display(),
                    "check_in": str(booking.check_in),
                    "check_out": str(booking.check_out),
                    "guests": booking.guests,
                    "num_nights": booking.num_nights,
                    "total_paid": str(booking.total_price),
                    "payment_id": payment_id or "N/A",
                    "email_sent_to": booking.user.email,
                },
            },
            status=status.HTTP_200_OK,
        )


class MyBookingsView(APIView):
    """
    GET /bookings/my/

    User dashboard — lists upcoming and past bookings.
    Shows can_cancel flag (only if check-in > 24 hours away).
    Auto-expires any timed-out holds.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Auto-expire timed-out pending holds
        for booking in Booking.objects.filter(user=request.user, status='pending'):
            booking.expire_if_needed()

        SHOW_STATUSES = ('confirmed', 'completed', 'cancelled')
        today = timezone.now().date()
        cutoff_24h = timezone.now() + timedelta(hours=24)

        upcoming = Booking.objects.select_related("room").filter(
            user=request.user,
            status__in=SHOW_STATUSES,
            check_in__gte=today,
        ).order_by("check_in")

        past = Booking.objects.select_related("room").filter(
            user=request.user,
            status__in=SHOW_STATUSES,
            check_in__lt=today,
        ).order_by("-check_in")

        def serialize_with_cancel(bookings):
            result = []
            for b in bookings:
                data = BookingSerializer(b).data
                can_cancel = (
                    b.status == 'confirmed'
                    and timezone.make_aware(
                        datetime.combine(b.check_in, dt_time.min)
                    ) > cutoff_24h
                )
                data["can_cancel"] = can_cancel
                result.append(data)
            return result

        return Response(
            {
                "upcoming": {
                    "count": upcoming.count(),
                    "bookings": serialize_with_cancel(upcoming),
                },
                "past": {
                    "count": past.count(),
                    "bookings": serialize_with_cancel(past),
                },
            },
            status=status.HTTP_200_OK,
        )


# ============================================================================
# PHASE 5: OTA Calendar API
# ============================================================================

class CalendarView(APIView):
    """
    GET /api/properties/{id}/calendar/
    Returns 30-day view of bookings, holds, and OTA blocks.
    """
    permission_classes = [AllowAny]

    def get(self, request, property_id):
        from datetime import timedelta
        today = timezone.now().date()
        end_date = today + timedelta(days=30)
        
        # Get rooms for this property
        rooms = Room.objects.filter(property_id=property_id, is_active=True)
        room_ids = rooms.values_list('id', flat=True)
        
        # Get bookings for these rooms
        bookings = Booking.objects.filter(
            room_id__in=room_ids,
            check_in__lt=end_date,
            check_out__gt=today,
            status__in=['confirmed', 'pending']
        )
        
        # Get OTA blocks
        blocks = OTABlock.objects.filter(
            room_id__in=room_ids,
            start_date__lt=end_date,
            end_date__gt=today
        )
        
        # Format response
        calendar_data = []
        for room in rooms:
            room_bookings = bookings.filter(room=room)
            room_blocks = blocks.filter(room=room)
            
            events = []
            for b in room_bookings:
                # Only include pending if hold hasn't expired
                if b.status == 'pending' and getattr(b, 'is_hold_expired', False):
                    continue
                    
                color = 'red' if b.status == 'confirmed' else 'yellow'
                events.append({
                    "type": "booking",
                    "status": "HELD" if b.status == "pending" else "CONFIRMED",
                    "start_date": b.check_in,
                    "end_date": b.check_out,
                    "color": color
                })
                
            for bl in room_blocks:
                events.append({
                    "type": "block",
                    "id": bl.id,
                    "start_date": bl.start_date,
                    "end_date": bl.end_date,
                    "reason": bl.reason,
                    "color": "grey"
                })
                
            calendar_data.append({
                "room_id": room.id,
                "room_name": room.name,
                "events": events
            })
            
        return Response(calendar_data)


class BlockRoomView(APIView):
    """
    POST /block/
    Employee endpoint to manually block a room.
    """
    permission_classes = [IsEmployee]

    def post(self, request):
        serializer = OTABlockSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UnblockRoomView(APIView):
    """
    POST /unblock/{id}/
    Employee endpoint to remove a manual block.
    """
    permission_classes = [IsEmployee]

    def post(self, request, pk):
        try:
            block = OTABlock.objects.get(pk=pk)
            block.delete()
            return Response({"message": "Block removed successfully."}, status=status.HTTP_200_OK)
        except OTABlock.DoesNotExist:
            return Response({"error": "Block not found."}, status=status.HTTP_404_NOT_FOUND)


# ============================================================================
# PAGE VIEWS (Template Rendering)
# ============================================================================

def search_page(request):
    """Render the room search page — passes DB-driven property list for the filter select."""
    properties = Property.objects.filter(is_active=True).order_by('name')
    return render(request, "rooms/search.html", {
        'properties': properties,
        'back_url': '/',
        'back_label': 'Back to home',
    })


def room_detail_page(request):
    """Render the room detail page template."""
    return render(request, "rooms/room_details.html", {
        'back_url': request.META.get('HTTP_REFERER', '/rooms/search/page/'),
        'back_label': 'Back',
    })


def my_bookings_page(request):
    """Render the my bookings page template."""
    return render(request, "bookings/my_bookings.html")


def confirmation_page(request):
    """Render the booking confirmation page template."""
    return render(request, "bookings/confirmation.html")
