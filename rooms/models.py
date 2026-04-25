"""
Models for rooms and bookings.

Room — stores hotel room details (city, type, price, capacity, amenities).
Booking — stores confirmed/pending/cancelled bookings with date ranges.
"""

import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Room(models.Model):
    """
    Hotel room available for booking.
    """

    ROOM_TYPE_CHOICES = [
        ("single", "Single"),
        ("double", "Double"),
        ("deluxe", "Deluxe"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(
        max_length=100,
        help_text="Room name or number (e.g., 'Ocean View Suite 301')",
    )
    city = models.CharField(
        max_length=100,
        db_index=True,
        help_text="City where the hotel/room is located.",
    )
    room_type = models.CharField(
        max_length=10,
        choices=ROOM_TYPE_CHOICES,
        db_index=True,
    )
    price_per_night = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price per night in INR.",
    )
    capacity = models.PositiveSmallIntegerField(
        help_text="Maximum number of guests.",
    )
    amenities = models.TextField(
        blank=True,
        default="",
        help_text="Comma-separated amenities (e.g., 'WiFi, AC, TV, Mini Bar').",
    )
    description = models.TextField(
        blank=True,
        default="",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only active rooms show up in search results.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "room"
        verbose_name_plural = "rooms"
        ordering = ["city", "price_per_night"]

    def __str__(self):
        return f"{self.name} ({self.city}) — ₹{self.price_per_night}/night"

    @property
    def amenities_list(self):
        """Return amenities as a list."""
        if not self.amenities:
            return []
        return [a.strip() for a in self.amenities.split(",") if a.strip()]


class RoomImage(models.Model):
    """
    Image for a hotel room. Supports multiple images per room
    with one marked as the primary/hero image.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(
        upload_to="room_images/",
        help_text="Upload a room photo (JPEG/PNG, max 5MB recommended).",
    )
    caption = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Optional caption for the image.",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="Primary image is shown as the hero/thumbnail.",
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order. Lower numbers appear first.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "room image"
        verbose_name_plural = "room images"
        ordering = ["order", "-is_primary", "created_at"]

    def __str__(self):
        tag = " [PRIMARY]" if self.is_primary else ""
        return f"Image for {self.room.name}{tag}"


class Booking(models.Model):
    """
    A booking ties a user to a room for specific dates.

    Status machine:
        PENDING   → hold created, payment not done yet
        CONFIRMED → payment successful
        EXPIRED   → hold timed out, never paid
        FAILED    → payment was attempted but failed
        CANCELLED → user cancelled after confirmation
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("expired", "Expired"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="bookings",
    )
    check_in = models.DateField()
    check_out = models.DateField()
    guests = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    hold_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the hold expires if payment is not completed.",
    )
    razorpay_order_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Razorpay order ID for this booking.",
    )
    booking_reference = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        unique=True,
        help_text="Human-readable booking reference (e.g., BK-20260424-A3F7).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "booking"
        verbose_name_plural = "bookings"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(check_out__gt=models.F("check_in")),
                name="check_out_after_check_in",
            ),
        ]

    def __str__(self):
        return f"Booking: {self.user.email} -> {self.room.name} ({self.check_in} to {self.check_out}) [{self.status}]"

    @property
    def num_nights(self):
        return (self.check_out - self.check_in).days

    @property
    def is_hold_expired(self):
        """Check if the hold has passed its expiry time."""
        if self.status != "pending":
            return False
        if self.hold_expires_at is None:
            return False
        return timezone.now() >= self.hold_expires_at

    def expire_if_needed(self):
        """
        Auto-expire this booking if the hold has timed out.
        Returns True if the booking was expired.
        """
        if self.is_hold_expired:
            self.status = "expired"
            self.save(update_fields=["status"])
            return True
        return False

    def generate_booking_reference(self):
        """
        Generate a human-readable booking reference like BK-20260424-A3F7.
        Called when booking is confirmed.
        """
        if self.booking_reference:
            return self.booking_reference
        date_part = timezone.now().strftime("%Y%m%d")
        random_part = secrets.token_hex(2).upper()  # 4 hex chars
        self.booking_reference = f"BK-{date_part}-{random_part}"
        self.save(update_fields=["booking_reference"])
        return self.booking_reference

