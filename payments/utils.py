"""
Razorpay client utilities and email helpers for payments.
"""

import hashlib
import hmac
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

import razorpay

logger = logging.getLogger(__name__)

# =========================================================================
# Razorpay Client
# =========================================================================

def get_razorpay_client():
    """
    Return a Razorpay client using current settings.
    Creates a fresh client each time to avoid stale credentials after .env changes.
    """
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def create_razorpay_order(amount_inr, booking_id):
    """
    Create a Razorpay order.

    Args:
        amount_inr: Amount in INR (Decimal or float)
        booking_id: Our booking UUID (used as receipt)

    Returns:
        dict with order details from Razorpay
    """
    client = get_razorpay_client()

    # Razorpay expects amount in paise (1 INR = 100 paise)
    amount_paise = int(float(amount_inr) * 100)

    order_data = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": str(booking_id),
        "payment_capture": 1,  # Auto-capture payment
    }

    order = client.order.create(data=order_data)
    logger.info("Razorpay order created: %s for Rs.%s", order["id"], amount_inr)
    return order


def verify_razorpay_signature(order_id, payment_id, signature):
    """
    Verify Razorpay payment signature using HMAC-SHA256.

    This is the ONLY proof that the payment is genuine.
    Razorpay signs: order_id + "|" + payment_id
    with the key_secret using SHA256.

    Returns True if signature is valid.
    """
    client = get_razorpay_client()

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        logger.warning("Signature verification failed for order %s", order_id)
        return False


def verify_webhook_signature(body, signature, webhook_secret):
    """
    Verify Razorpay webhook signature.

    Args:
        body: Raw request body (bytes)
        signature: X-Razorpay-Signature header value
        webhook_secret: Webhook secret from Razorpay dashboard

    Returns True if signature is valid.
    """
    expected = hmac.new(
        key=webhook_secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


# =========================================================================
# Email: Booking Confirmation
# =========================================================================

def send_booking_confirmation_email(booking):
    """
    Send booking confirmation email via Gmail SMTP.
    """
    try:
        subject = f"Booking Confirmed - {booking.booking_reference}"

        html_message = render_to_string(
            "emails/booking_confirmation.html",
            {
                "booking": booking,
                "room": booking.room,
                "user": booking.user,
            },
        )

        send_mail(
            subject=subject,
            message=f"Your booking {booking.booking_reference} is confirmed. "
                    f"Room: {booking.room.name}, Check-in: {booking.check_in}, "
                    f"Check-out: {booking.check_out}, Total: Rs.{booking.total_price}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.user.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info("Confirmation email sent to %s for %s", booking.user.email, booking.booking_reference)

    except Exception as e:
        # Email failure should NOT block the booking confirmation
        logger.error("Failed to send confirmation email to %s: %s", booking.user.email, str(e))
