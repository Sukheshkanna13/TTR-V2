"""
Custom User model and OTP model for hotel_booking.
Uses email as the unique identifier instead of username.
OTP is stored directly in PostgreSQL with an expiry timestamp.
"""

import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model.

    - email is the unique identifier (no username)
    - is_active defaults to False (activated after OTP verification)
    - Password is hashed with bcrypt (configured in settings.PASSWORD_HASHERS)
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email = models.EmailField(
        "email address",
        unique=True,
        db_index=True,
        error_messages={
            "unique": "A user with that email already exists.",
        },
    )
    full_name = models.CharField(
        "full name",
        max_length=150,
    )
    phone = models.CharField(
        "phone number",
        max_length=15,
    )
    is_active = models.BooleanField(
        "active",
        default=False,
        help_text=(
            "Designates whether this user should be treated as active. "
            "Set to True after OTP email verification."
        ),
    )
    is_staff = models.BooleanField(
        "staff status",
        default=False,
        help_text="Designates whether the user can log into the admin site.",
    )
    date_joined = models.DateTimeField(
        "date joined",
        default=timezone.now,
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.email


class OTP(models.Model):
    """
    OTP model — stores verification codes directly in PostgreSQL.

    Each OTP is tied to a user's email, has a 6-digit code,
    tracks attempts, and expires after a configurable duration.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email = models.EmailField(
        db_index=True,
    )
    code = models.CharField(
        max_length=6,
    )
    attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of failed verification attempts.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "OTP"
        verbose_name_plural = "OTPs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP for {self.email} (expires {self.expires_at})"

    @property
    def is_expired(self):
        """Check if this OTP has passed its expiry time."""
        return timezone.now() >= self.expires_at

    @property
    def is_blocked(self):
        """Check if max verification attempts have been reached."""
        max_attempts = getattr(settings, "OTP_MAX_ATTEMPTS", 3)
        return self.attempts >= max_attempts

    def save(self, *args, **kwargs):
        """Auto-set expires_at if not provided."""
        if not self.expires_at:
            expiry_minutes = getattr(settings, "OTP_EXPIRY_MINUTES", 10)
            self.expires_at = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
        super().save(*args, **kwargs)


class PendingRegistration(models.Model):
    """
    Temporary store for signup data before OTP is verified.

    Flow:
      Step 1: POST /accounts/register/      → store email/name/phone here, send OTP
      Step 2: POST /accounts/verify-otp/    → verify OTP, mark email_verified=True
      Step 3: POST /accounts/set-password/  → create real User, delete this row

    No User row is ever created until all 3 steps complete.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)
    email_verified = models.BooleanField(
        default=False,
        help_text="Set to True once OTP is successfully verified.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="This pending record expires if not completed in time.",
    )

    class Meta:
        verbose_name = "pending registration"
        verbose_name_plural = "pending registrations"

    def __str__(self):
        return f"PendingRegistration({self.email}, verified={self.email_verified})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def save(self, *args, **kwargs):
        if not self.expires_at:
            # Expire 30 minutes after creation (3x OTP window)
            self.expires_at = timezone.now() + timezone.timedelta(minutes=30)
        super().save(*args, **kwargs)


class LoginAttempt(models.Model):
    """
    Tracks failed login attempts per email in PostgreSQL.
    Used to lock accounts after too many failures.
    """

    email = models.EmailField(
        unique=True,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(
        default=0,
    )
    locked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, the account is locked until this time.",
    )
    last_attempt_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "login attempt"
        verbose_name_plural = "login attempts"

    def __str__(self):
        return f"LoginAttempt for {self.email} ({self.attempts} tries)"

    @property
    def is_locked(self):
        """Check if the account is currently locked."""
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        # If lock has expired, reset it
        if self.locked_until and timezone.now() >= self.locked_until:
            self.attempts = 0
            self.locked_until = None
            self.save(update_fields=["attempts", "locked_until"])
        return False


class UserProfile(models.Model):
    """
    Profile for user roles, financial access levels, employee settings,
    and guest loyalty programme.
    """
    ROLE_CHOICES = [
        ('guest', 'Guest'),
        ('employee', 'Employee'),
        ('employee_admin', 'Employee Admin'),
        ('super_admin', 'Super Admin'),
    ]
    FIN_LEVEL_CHOICES = [
        ('A', 'Level A (Full Financial Access)'),
        ('B', 'Level B (Limited Financial Access)'),
        ('C', 'Level C (No Financial Access)'),
    ]
    TIER_CHOICES = [
        ('bronze', 'Bronze'),
        ('silver', 'Silver'),
        ('gold', 'Gold'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='userprofile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='guest')
    fin_level = models.CharField(max_length=1, choices=FIN_LEVEL_CHOICES, null=True, blank=True)
    assigned_properties = models.ManyToManyField('rooms.Property', blank=True, related_name='assigned_employees')
    must_change_password = models.BooleanField(default=False)
    loyalty_points = models.PositiveIntegerField(default=0)
    loyalty_tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='bronze')

    # Employee provenance + lifecycle
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='employees_created',
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='employees_revoked',
    )

    def __str__(self):
        return f"{self.user.email} Profile ({self.role})"

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def can_hard_delete(self):
        """A record may be permanently deleted only if it was never used."""
        return self.user.last_login is None

    def revoke(self, by_user):
        """Soft-revoke: disable login, strip access, keep the record for audit."""
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assigned_properties.clear()
        self.revoked_at = timezone.now()
        self.revoked_by = by_user
        self.save(update_fields=['revoked_at', 'revoked_by'])

    def reinstate(self):
        """Reverse a revoke: clear the revoked stamp and re-enable login."""
        self.user.is_active = True
        self.user.save(update_fields=['is_active'])
        self.revoked_at = None
        self.revoked_by = None
        self.save(update_fields=['revoked_at', 'revoked_by'])

    def recalculate_tier(self):
        """Update loyalty_tier based on current loyalty_points and save."""
        if self.loyalty_points >= 1500:
            self.loyalty_tier = 'gold'
        elif self.loyalty_points >= 500:
            self.loyalty_tier = 'silver'
        else:
            self.loyalty_tier = 'bronze'
        self.save(update_fields=['loyalty_tier'])
