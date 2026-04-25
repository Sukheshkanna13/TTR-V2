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
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Booking, Room
from .serializers import (
    BookingSerializer,
    HoldRoomSerializer,
    RoomSerializer,
    SearchSerializer,
)

logger = logging.getLogger(__name__)

# Hold duration in minutes
HOLD_DURATION_MINUTES = 10


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

    return Booking.objects.filter(
        check_in__lt=check_out,
        check_out__gt=check_in,
    ).filter(
        # Confirmed bookings always block
        Q(status="confirmed")
        |
        # Pending holds block only if they haven't expired
        Q(status="pending", hold_expires_at__gt=now)
    ).values_list("room_id", flat=True)


# =========================================================================
# PHASE 2: Room Search
# =========================================================================

class SearchRoomsView(APIView):
    """
    GET /rooms/search/

    Search for available rooms with filters and sorting.
    All filtering happens in a single database query.

    Required params: city, check_in, check_out, guests
    Optional params: room_type, min_price, max_price, sort
    """

    permission_classes = [AllowAny]

    def get(self, request):
        serializer = SearchSerializer(data=request.query_params)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        city = data["city"]
        check_in = data["check_in"]
        check_out = data["check_out"]
        guests = data["guests"]

        # Optional filters
        room_type = data.get("room_type")
        min_price = data.get("min_price")
        max_price = data.get("max_price")
        sort = data.get("sort")

        # ----------------------------------------------------------------
        # SINGLE QUERY: find available rooms
        # ----------------------------------------------------------------

        # Step 1: Get IDs of rooms that are booked OR held
        unavailable_ids = get_unavailable_room_ids(check_in, check_out)

        # Step 2: Active rooms in the city with enough capacity, excluding blocked ones
        rooms = Room.objects.filter(
            is_active=True,
            city__iexact=city,
            capacity__gte=guests,
        ).exclude(
            id__in=unavailable_ids,
        )

        # Step 3: Apply optional filters (same query, no extra DB hits)
        if room_type:
            rooms = rooms.filter(room_type=room_type)
        if min_price is not None:
            rooms = rooms.filter(price_per_night__gte=min_price)
        if max_price is not None:
            rooms = rooms.filter(price_per_night__lte=max_price)

        # Step 4: Apply sorting
        if sort == "price_desc":
            rooms = rooms.order_by("-price_per_night")
        else:
            rooms = rooms.order_by("price_per_night")

        # Serialize and respond
        room_list = RoomSerializer(rooms, many=True, context={"request": request}).data
        num_nights = (check_out - check_in).days

        if not room_list:
            return Response(
                {
                    "message": "No rooms available for these dates. Try different dates or a different city.",
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
                "message": f"{len(room_list)} room(s) found.",
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
            room = Room.objects.get(id=room_id, is_active=True)
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

        # Calculate total price
        num_nights = (check_out - check_in).days
        total_price = room.price_per_night * num_nights

        # ----------------------------------------------------------------
        # DOUBLE-BOOKING PROTECTION
        # Atomic transaction + select_for_update to lock rows
        # ----------------------------------------------------------------
        try:
            with transaction.atomic():
                now = timezone.now()

                # Lock all bookings for this room that could overlap
                overlapping = Booking.objects.select_for_update().filter(
                    room=room,
                    check_in__lt=check_out,
                    check_out__gt=check_in,
                ).filter(
                    Q(status="confirmed")
                    | Q(status="pending", hold_expires_at__gt=now)
                )

                if overlapping.exists():
                    return Response(
                        {
                            "error": "Sorry, this room was just taken for the selected dates. Please pick another room.",
                            "code": "ROOM_TAKEN",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                # Room is available — create PENDING hold
                hold_expires_at = now + timedelta(minutes=HOLD_DURATION_MINUTES)

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

        return Response(
            {
                "message": f"Room held for {HOLD_DURATION_MINUTES} minutes. Please complete payment.",
                "booking": BookingSerializer(booking).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ProcessPaymentView(APIView):
    """
    POST /bookings/<id>/pay/

    DEV/FALLBACK: Quick-confirm a booking without Razorpay.
    In production, use /payments/create-order/ + /payments/verify/ instead.

    Kept for testing purposes — lets you confirm a booking directly.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):
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

        booking.status = "cancelled"
        booking.hold_expires_at = None
        booking.save(update_fields=["status", "hold_expires_at"])

        logger.info("Booking cancelled: %s cancelled %s", request.user.email, booking.room.name)

        return Response(
            {
                "message": "Booking cancelled successfully.",
                "booking": BookingSerializer(booking).data,
            },
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
        from datetime import timedelta as td

        all_bookings = Booking.objects.select_related("room").filter(
            user=request.user,
        ).order_by("-created_at")

        # Auto-expire any timed-out holds
        for booking in all_bookings:
            booking.expire_if_needed()

        # Re-fetch after potential status changes
        today = timezone.now().date()
        cutoff_24h = timezone.now() + td(hours=24)

        upcoming = Booking.objects.select_related("room").filter(
            user=request.user,
            check_in__gte=today,
        ).order_by("check_in")

        past = Booking.objects.select_related("room").filter(
            user=request.user,
            check_in__lt=today,
        ).order_by("-check_in")

        def serialize_with_cancel(bookings):
            result = []
            for b in bookings:
                data = BookingSerializer(b).data
                # Can cancel only if status allows AND check-in is > 24h away
                can_cancel = (
                    b.status in ("pending", "confirmed")
                    and timezone.make_aware(
                        timezone.datetime.combine(b.check_in, timezone.datetime.min.time())
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
