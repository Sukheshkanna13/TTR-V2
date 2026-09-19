import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from rooms.models import Booking
from payments.models import Payment
from payments.utils import send_booking_confirmation_email, send_invoice_email

logger = logging.getLogger(__name__)


def confirm_booking_and_payment(
    order_id: str,
    payment_id: str,
    signature: str = "",
    captured_amount_paise: Optional[int] = None,
    caller: str = "browser",
) -> Dict[str, Any]:
    """
    Atomic, idempotent booking confirmation service.
    Locks the Booking row, reconciles paid amount, updates status to confirmed,
    marks Payment captured, and triggers one-time invoice/confirmation dispatches.
    """
    with transaction.atomic():
        try:
            booking = Booking.objects.select_for_update().get(razorpay_order_id=order_id)
        except Booking.DoesNotExist:
            return {"success": False, "error": "Booking not found.", "code": "NOT_FOUND"}

        # 1. Already confirmed? Idempotent return (prevents race with webhook)
        if booking.status == "confirmed":
            logger.info("Idempotent check: Booking %s already confirmed by previous caller (%s).", booking.id, caller)
            return {"success": True, "already_confirmed": True, "booking": booking}

        # 2. Cancelled check
        if booking.status == "cancelled":
            logger.error("RECONCILIATION NEEDED: Payment arrived for cancelled booking %s", booking.id)
            return {"success": False, "error": "Booking is cancelled.", "code": "CANCELLED"}

        # 3. Amount verification (PAY-01)
        expected_paise = int(booking.payable_amount * 100)
        if captured_amount_paise is not None and captured_amount_paise != expected_paise:
            logger.error(
                "PAYMENT RECONCILIATION FAILED for booking %s: expected %s paise, received %s paise",
                booking.id, expected_paise, captured_amount_paise,
            )
            Payment.objects.filter(razorpay_order_id=order_id).update(
                razorpay_payment_id=payment_id,
                status="failed",
            )
            booking.release_hold("payment_failed")
            return {
                "success": False,
                "error": "Payment amount does not match booking total.",
                "code": "AMOUNT_MISMATCH",
            }

        # 4. Check for conflicts if hold had lapsed
        if booking.status != "pending":
            conflict = Booking.objects.filter(
                room=booking.room,
                status="confirmed",
                check_in__lt=booking.check_out,
                check_out__gt=booking.check_in,
            ).exclude(pk=booking.pk).exists()

            if conflict:
                logger.error("Room conflict for lapsed booking %s upon payment capture", booking.id)
                Payment.objects.filter(razorpay_order_id=order_id).update(
                    razorpay_payment_id=payment_id, status="captured",
                )
                return {"success": False, "error": "Room re-booked during lapsed hold.", "code": "ROOM_CONFLICT"}

        # 5. Confirm booking & capture payment atomically
        booking.status = "confirmed"
        booking.hold_expires_at = None
        booking.save(update_fields=["status", "hold_expires_at"])
        booking.generate_booking_reference()
        booking.compute_tax()

        # Mark applied coupon as redeemed
        if booking.coupon:
            from django.utils import timezone
            from loyalty.models import Coupon
            booking.coupon.status = Coupon.STATUS_REDEEMED
            booking.coupon.used_at = timezone.now()
            booking.coupon.save(update_fields=["status", "used_at"])

        Payment.objects.filter(razorpay_order_id=order_id).update(
            razorpay_payment_id=payment_id,
            razorpay_signature=signature,
            payment_method=Payment.METHOD_RAZORPAY,
            status="captured",
        )

    # 6. Dispatches outside atomic block (Async background task execution for sub-80ms response)
    try:
        from django_q.tasks import async_task
        async_task("payments.utils.send_booking_confirmation_email", str(booking.id))
        async_task("payments.utils.send_invoice_email", str(booking.id))
        async_task(
            "rooms.tasks.sync_ota_inventory_for_dates",
            booking.room.room_type,
            booking.check_in.isoformat(),
            booking.check_out.isoformat(),
            booking.room.property_id,
        )
    except Exception as e:
        logger.warning("Error enqueueing post-confirmation async tasks for booking %s: %s", booking.id, e)
        # Fallback to direct synchronous execution in case django-q is unavailable
        try:
            send_booking_confirmation_email(booking)
            send_invoice_email(booking)
        except Exception as direct_err:
            logger.error("Direct email dispatch fallback failed: %s", direct_err)

    return {"success": True, "already_confirmed": False, "booking": booking}
