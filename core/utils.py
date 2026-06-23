import logging
from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

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


# =========================================================================
# Email: Invoice (post-payment)
# =========================================================================

def send_invoice_email(booking):
    """
    Send an HTML invoice email after payment is confirmed.

    Renders templates/emails/invoice.html and delivers it via Gmail SMTP.
    Failures are logged but never re-raised — they must not break the
    payment confirmation response.
    """
    try:
        num_nights = (booking.check_out - booking.check_in).days
        subject = (
            f"Booking Confirmed — {booking.room.name} "
            f"| Ref: {booking.booking_reference}"
        )
        html_body = render_to_string(
            "emails/invoice.html",
            {
                "booking": booking,
                "room": booking.room,
                "guest": booking.user,
                "num_nights": num_nights,
            },
        )
        email = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[booking.user.email],
        )
        email.content_subtype = "html"
        email.send(fail_silently=False)
        logger.info(
            "Invoice email sent to %s for booking %s",
            booking.user.email,
            booking.booking_reference,
        )
    except Exception as e:
        logger.error(
            "Failed to send invoice email to %s (booking %s): %s",
            booking.user.email,
            booking.booking_reference,
            str(e),
        )

# =========================================================================
# Email: Hold Notification (to Admins)
# =========================================================================

def send_hold_notification_email(booking):
    """
    Send an email notification to superadmins and assigned employees
    when a new room hold is requested.
    """
    try:
        from accounts.models import UserProfile
        superadmins = UserProfile.objects.filter(role='super_admin', user__is_active=True)
        employees = UserProfile.objects.filter(
            role__in=['employee', 'employee_admin'], 
            assigned_properties=booking.room.property, 
            user__is_active=True
        )
        
        emails = set()
        for p in superadmins:
            if p.user.email:
                emails.add(p.user.email)
        for p in employees:
            if p.user.email:
                emails.add(p.user.email)

        if emails:
            subject = f"New Room Hold Request - {booking.booking_reference}"
            message = (
                f"Guest {booking.user.full_name} ({booking.user.email}) has requested a hold "
                f"for {booking.room.name} ({booking.room.property.name}) "
                f"from {booking.check_in} to {booking.check_out}.\n\n"
                f"Please review and approve this hold in the Admin Dashboard."
            )
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(emails),
                fail_silently=False,
            )
            logger.info("Admin hold notification sent to %s admins for %s", len(emails), booking.booking_reference)
            
    except Exception as e:
        logger.error("Failed to send admin hold notification for %s: %s", booking.booking_reference, str(e))
