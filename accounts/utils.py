"""
OTP generation and database helper utilities.
All OTP operations use PostgreSQL — no Redis needed.
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


# =============================================================================
# OTP GENERATION
# =============================================================================

def generate_otp() -> str:
    """
    Generate a cryptographically secure 6-digit OTP using secrets module.
    """
    length = getattr(settings, "OTP_LENGTH", 6)
    lower = 10 ** (length - 1)
    upper = (10 ** length) - 1
    return str(secrets.randbelow(upper - lower + 1) + lower)


# =============================================================================
# OTP DATABASE OPERATIONS
# =============================================================================

def create_and_store_otp(email: str) -> str:
    """
    Generate a new OTP, store it in PostgreSQL, and return the code.
    Deletes any existing OTPs for this email first.
    """
    from .models import OTP
    email = normalize_email(email)

    # Remove any old OTPs for this email
    OTP.objects.filter(email=email).delete()

    # Create new OTP with expiry
    otp_code = generate_otp()
    expiry_minutes = getattr(settings, "OTP_EXPIRY_MINUTES", 10)
    expires_at = timezone.now() + timedelta(minutes=expiry_minutes)

    OTP.objects.create(
        email=email,
        code=otp_code,
        expires_at=expires_at,
    )

    return otp_code


def verify_otp(email: str, submitted_code: str) -> dict:
    """
    Verify the submitted OTP against the database.

    Returns a dict with:
        - success (bool)
        - error (str or None)
        - code (str or None) — error code for frontend handling
    """
    from .models import OTP
    email = normalize_email(email)

    try:
        otp = OTP.objects.get(email=email)
    except OTP.DoesNotExist:
        return {
            "success": False,
            "error": "No verification code found. Please request a new one.",
            "code": "OTP_NOT_FOUND",
        }

    # Check if expired
    if otp.is_expired:
        otp.delete()
        return {
            "success": False,
            "error": "Your verification code has expired. Please request a new one.",
            "code": "OTP_EXPIRED",
        }

    # Check if blocked (too many attempts)
    if otp.is_blocked:
        return {
            "success": False,
            "error": "Too many failed attempts. Please request a new verification code.",
            "code": "OTP_BLOCKED",
        }

    # Check the code
    if submitted_code != otp.code:
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        max_attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 3)
        remaining = max_attempts - otp.attempts
        return {
            "success": False,
            "error": f"Invalid verification code. {remaining} attempt(s) remaining.",
            "code": "OTP_INVALID",
        }

    # Success! Delete the OTP so it can't be reused
    otp.delete()
    return {"success": True, "error": None, "code": None}


# =============================================================================
# LOGIN ATTEMPT TRACKING (Database)
# =============================================================================

def check_login_lock(email: str) -> dict:
    """
    Returns {'locked': bool, 'remaining_minutes': int}.
    remaining_minutes is 0 when not locked.
    """
    from .models import LoginAttempt
    email = normalize_email(email)

    try:
        attempt = LoginAttempt.objects.get(email=email)
        if attempt.is_locked:
            remaining = max(0, int((attempt.locked_until - timezone.now()).total_seconds() / 60)) + 1
            return {'locked': True, 'remaining_minutes': remaining}
        return {'locked': False, 'remaining_minutes': 0}
    except LoginAttempt.DoesNotExist:
        return {'locked': False, 'remaining_minutes': 0}


def record_failed_login(email: str) -> int:
    """
    Record a failed login attempt. Lock the account if threshold reached.
    Returns the new attempt count.
    """
    from .models import LoginAttempt
    email = normalize_email(email)

    attempt, created = LoginAttempt.objects.get_or_create(email=email)

    if not created:
        attempt.attempts += 1
    else:
        attempt.attempts = 1

    max_attempts = getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)
    lock_minutes = getattr(settings, "LOGIN_LOCK_DURATION_MINUTES", 15)

    # Lock the account if threshold reached
    if attempt.attempts >= max_attempts:
        attempt.locked_until = timezone.now() + timedelta(minutes=lock_minutes)

    attempt.save()
    return attempt.attempts


def reset_login_attempts(email: str) -> None:
    """Clear login attempt counters after a successful login."""
    from .models import LoginAttempt
    email = normalize_email(email)

    LoginAttempt.objects.filter(email=email).delete()


# =============================================================================
# EMAIL SENDING (Direct via Gmail SMTP)
# =============================================================================

def send_otp_email(email: str, otp_code: str) -> bool:
    """
    Send OTP verification email directly via Gmail SMTP.
    No background task — sends immediately.

    Returns True if sent successfully, False otherwise.
    """
    subject = "Your Hotel Booking Verification Code"

    # Try to use the HTML template, fall back to plain text
    try:
        html_message = render_to_string(
            "emails/otp_email.html",
            {"otp": otp_code, "year": timezone.now().year},
        )
        plain_message = strip_tags(html_message)
    except Exception:
        # Fallback: simple plain-text email
        html_message = None
        plain_message = (
            f"Your Hotel Booking verification code is: {otp_code}\n\n"
            f"This code expires in 10 minutes.\n"
            f"If you didn't request this, please ignore this email."
        )

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info("OTP email sent to %s", email)
        return True
    except Exception as e:
        logger.error("Failed to send OTP email to %s: %s", email, str(e))
        return False
