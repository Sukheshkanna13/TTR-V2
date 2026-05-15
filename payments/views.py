"""
API views for Razorpay payment integration.

Endpoints:
    POST /payments/create-order/  — Create Razorpay order for a pending booking
    POST /payments/verify/        — Verify payment signature from browser
    POST /payments/webhook/       — Razorpay server-to-server webhook
"""

import json
import logging

from django.conf import settings
from django.shortcuts import render
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_q.tasks import async_task

from rooms.models import Booking
from rooms.serializers import BookingSerializer

from .models import Payment
from .serializers import CreateOrderSerializer, VerifyPaymentSerializer
from .utils import (
    award_loyalty_points,
    create_razorpay_order,
    send_booking_confirmation_email,
    send_invoice_email,
    verify_razorpay_signature,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)


class CreateOrderView(APIView):
    """
    POST /payments/create-order/

    1. Receives booking_id
    2. Validates booking is PENDING and not expired
    3. Creates Razorpay order via API
    4. Saves order_id to booking
    5. Returns order details for the Razorpay checkout popup
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        booking_id = serializer.validated_data["booking_id"]

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

        # Must be PENDING
        if booking.status != "pending":
            return Response(
                {"error": f"Cannot create payment for booking with status: {booking.get_status_display()}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check hold expiry
        if booking.expire_if_needed():
            return Response(
                {
                    "error": "Your hold has expired. Please search and book again.",
                    "code": "HOLD_EXPIRED",
                },
                status=status.HTTP_410_GONE,
            )

        # Create Razorpay order
        try:
            order = create_razorpay_order(
                amount_inr=booking.total_price,
                booking_id=booking.id,
            )
        except Exception as e:
            logger.error("Razorpay order creation failed: %s", str(e))
            return Response(
                {"error": "Payment service temporarily unavailable. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Save order_id to booking
        booking.razorpay_order_id = order["id"]
        booking.save(update_fields=["razorpay_order_id"])

        # Create payment record
        Payment.objects.create(
            booking=booking,
            razorpay_order_id=order["id"],
            amount=booking.total_price,
            status="created",
        )

        logger.info(
            "Razorpay order %s created for booking %s (Rs.%s)",
            order["id"],
            booking.id,
            booking.total_price,
        )

        return Response(
            {
                "message": "Order created. Proceed to payment.",
                "order": {
                    "order_id": order["id"],
                    "amount": order["amount"],  # in paise
                    "currency": order["currency"],
                    "key_id": settings.RAZORPAY_KEY_ID,  # Frontend needs this
                },
                "booking": {
                    "id": str(booking.id),
                    "room_name": booking.room.name,
                    "check_in": str(booking.check_in),
                    "check_out": str(booking.check_out),
                    "total_price": str(booking.total_price),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyPaymentView(APIView):
    """
    POST /payments/verify/

    1. Receives razorpay_order_id, razorpay_payment_id, razorpay_signature
    2. Verifies HMAC-SHA256 signature (CRITICAL — only proof payment is real)
    3. If valid → CONFIRMED, save payment, generate reference, send email
    4. If invalid → BLOCKED, booking stays PENDING
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order_id = serializer.validated_data["razorpay_order_id"]
        payment_id = serializer.validated_data["razorpay_payment_id"]
        signature = serializer.validated_data["razorpay_signature"]

        # Find the booking by Razorpay order ID
        try:
            booking = Booking.objects.select_related("room", "user").get(
                razorpay_order_id=order_id,
                user=request.user,
            )
        except Booking.DoesNotExist:
            return Response(
                {"error": "Booking not found for this order."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Already confirmed? Don't double-process
        if booking.status == "confirmed":
            return Response(
                {
                    "message": "Booking is already confirmed.",
                    "booking": BookingSerializer(booking).data,
                },
                status=status.HTTP_200_OK,
            )

        # Must be PENDING
        if booking.status != "pending":
            return Response(
                {"error": f"Cannot verify payment for booking with status: {booking.get_status_display()}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ----------------------------------------------------------------
        # SIGNATURE VERIFICATION (CRITICAL)
        # ----------------------------------------------------------------
        if not verify_razorpay_signature(order_id, payment_id, signature):
            # Update payment record as failed
            Payment.objects.filter(
                razorpay_order_id=order_id,
            ).update(
                razorpay_payment_id=payment_id,
                razorpay_signature=signature,
                status="failed",
            )

            logger.warning(
                "Payment verification FAILED for order %s, user %s",
                order_id,
                request.user.email,
            )

            return Response(
                {
                    "error": "Payment verification failed. Please try again.",
                    "code": "SIGNATURE_INVALID",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ----------------------------------------------------------------
        # PAYMENT VERIFIED — Confirm booking
        # ----------------------------------------------------------------

        # Update booking
        booking.status = "confirmed"
        booking.hold_expires_at = None
        booking.save(update_fields=["status", "hold_expires_at"])

        # Generate booking reference
        booking.generate_booking_reference()

        # Update payment record
        Payment.objects.filter(
            razorpay_order_id=order_id,
        ).update(
            razorpay_payment_id=payment_id,
            razorpay_signature=signature,
            status="captured",
        )

        logger.info(
            "Payment verified: order=%s, payment=%s, booking=%s, ref=%s",
            order_id,
            payment_id,
            booking.id,
            booking.booking_reference,
        )

        # Send confirmation email (async-safe, won't block on failure)
        send_booking_confirmation_email(booking)

        # Send invoice email and award loyalty points (both wrapped in try/except)
        send_invoice_email(booking)
        award_loyalty_points(booking)

        # Queue WhatsApp confirmation
        if booking.user.phone:
            async_task(
                'core.tasks.send_whatsapp_message',
                phone=booking.user.phone,
                template_name='booking_confirmed',
                template_data={
                    "name": booking.user.full_name,
                    "reference": booking.booking_reference,
                    "check_in": str(booking.check_in),
                    "hotel": booking.room.property.name if hasattr(booking.room, 'property') else "Temple Towns"
                }
            )

        return Response(
            {
                "message": "Payment successful! Your booking is confirmed.",
                "booking": BookingSerializer(booking).data,
            },
            status=status.HTTP_200_OK,
        )


class WebhookView(APIView):
    """
    POST /payments/webhook/

    Razorpay server-to-server webhook — catches cases where browser
    crashed after payment but before Django confirmed it.

    - No authentication required (Razorpay calls this directly)
    - Verifies webhook signature for security
    - Idempotent: if already CONFIRMED, returns 200 without changes
    """

    permission_classes = [AllowAny]

    def post(self, request):
        # Get the webhook signature from header
        signature = request.META.get("HTTP_X_RAZORPAY_SIGNATURE", "")

        if not signature:
            return Response(
                {"error": "Missing signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify webhook signature
        webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")

        if not webhook_secret:
            logger.error("RAZORPAY_WEBHOOK_SECRET not configured.")
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not verify_webhook_signature(request.body, signature, webhook_secret):
            logger.warning("Webhook signature verification failed.")
            return Response(
                {"error": "Invalid signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse the event
        try:
            event = json.loads(request.body)
        except json.JSONDecodeError:
            return Response(
                {"error": "Invalid payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = event.get("event", "")

        # We only care about payment.captured
        if event_type != "payment.captured":
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        # Extract payment details from the event
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = payment_entity.get("order_id", "")
        payment_id = payment_entity.get("id", "")

        if not order_id:
            return Response(
                {"error": "Missing order_id in payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find the booking
        try:
            booking = Booking.objects.select_related("room", "user").get(
                razorpay_order_id=order_id,
            )
        except Booking.DoesNotExist:
            logger.warning("Webhook: No booking found for order %s", order_id)
            return Response(status=status.HTTP_200_OK)

        # Already confirmed? Don't double-process
        if booking.status == "confirmed":
            logger.info("Webhook: Booking %s already confirmed, skipping.", booking.id)
            return Response({"status": "already_confirmed"}, status=status.HTTP_200_OK)

        # Only process PENDING bookings
        if booking.status == "pending":
            booking.status = "confirmed"
            booking.hold_expires_at = None
            booking.save(update_fields=["status", "hold_expires_at"])

            # Generate booking reference
            booking.generate_booking_reference()

            # Update payment record
            Payment.objects.filter(
                razorpay_order_id=order_id,
            ).update(
                razorpay_payment_id=payment_id,
                status="captured",
            )

            logger.info(
                "Webhook confirmed booking %s (order: %s, ref: %s)",
                booking.id,
                order_id,
                booking.booking_reference,
            )

            # Send confirmation email
            send_booking_confirmation_email(booking)

            # Send invoice email and award loyalty points (both wrapped in try/except)
            send_invoice_email(booking)
            award_loyalty_points(booking)

            # Queue WhatsApp confirmation
            if booking.user.phone:
                async_task(
                    'core.tasks.send_whatsapp_message',
                    phone=booking.user.phone,
                    template_name='booking_confirmed',
                    template_data={
                        "name": booking.user.full_name,
                        "reference": booking.booking_reference,
                        "check_in": str(booking.check_in),
                        "hotel": booking.room.property.name if hasattr(booking.room, 'property') else "Temple Towns"
                    }
                )

        return Response({"status": "processed"}, status=status.HTTP_200_OK)


# ============================================================================
# PAGE VIEWS (Template Rendering)
# ============================================================================

def checkout_page(request):
    """Render the checkout page template."""
    return render(request, "payments/checkout.html")
