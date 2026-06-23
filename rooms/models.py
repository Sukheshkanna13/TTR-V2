"""
Models for rooms and bookings.

Room — stores hotel room details (city, type, price, capacity, amenities).
Booking — stores confirmed/pending/cancelled bookings with date ranges.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
import builtins

if TYPE_CHECKING:
    from superadmin.models import PropertyTaxConfig


class Property(models.Model):
    """
    A hotel property (e.g., Pondicherry, Auroville, Bengaluru).
    """
    objects = models.Manager()

    # Type annotations for static typing / Pyrefly
    rooms: models.Manager
    tax_config: "PropertyTaxConfig"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address = models.TextField(blank=True, default="")
    whatsapp_number = models.CharField(
        max_length=20, 
        blank=True, 
        default="",
        help_text="WhatsApp number for notifications"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "property"
        verbose_name_plural = "properties"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.city})"


class RoomManager(models.Manager):
    """Manager for Room. Owns the home-page featured-stays selection rule."""

    def featured_for_home(self, min_count=3):
        """Return the rooms for the home carousel.

        Featured (starred) rooms first, ordered by their property's rating
        (highest first, nulls last) then newest. If fewer than ``min_count``
        are featured, fill the remaining slots with the highest-rated
        non-featured rooms. Only active, available rooms that have at least
        one image are eligible.
        """
        from django.db.models import F

        pool = list(
            self.get_queryset()
            .filter(is_active=True, operational_status=Room.STATUS_AVAILABLE)
            .select_related("property")
            .prefetch_related("images")
            .order_by(F("rating").desc(nulls_last=True), "-created_at")
        )

        featured = [r for r in pool if r.is_featured]
        if len(featured) >= min_count:
            return featured

        result = list(featured)
        featured_ids = {r.id for r in featured}
        for room in pool:
            if len(result) >= min_count:
                break
            if room.id not in featured_ids:
                result.append(room)
        return result


class Room(models.Model):
    """
    Hotel room available for booking.
    """

    ROOM_TYPE_CHOICES = [
        ("single", "Single"),
        ("double", "Double"),
        ("deluxe", "Deluxe"),
    ]

    objects = RoomManager()

    # Type annotations for static typing / Pyrefly
    rates: models.Manager
    images: models.Manager
    bookings: models.Manager
    ota_blocks: models.Manager

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="rooms",
        null=True,
        blank=True,
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
    STATUS_AVAILABLE = "available"
    STATUS_CLEANING = "cleaning"
    STATUS_MAINTENANCE = "maintenance"
    STATUS_OUT_OF_ORDER = "out_of_order"

    OPERATIONAL_STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Available"),
        (STATUS_CLEANING, "Cleaning"),
        (STATUS_MAINTENANCE, "Maintenance"),
        (STATUS_OUT_OF_ORDER, "Out of Order"),
    ]

    is_active = models.BooleanField(
        default=True,
        help_text="Only active rooms show up in search results.",
    )
    operational_status = models.CharField(
        max_length=20,
        choices=OPERATIONAL_STATUS_CHOICES,
        default=STATUS_AVAILABLE,
        db_index=True,
        help_text="Current operational state of the room.",
    )
    is_featured = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Show this room in the Featured Stays carousel on the home page.",
    )
    rating = models.DecimalField(
        max_digits=2, decimal_places=1, default="4.5",
        help_text="Room rating out of 5.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "room"
        verbose_name_plural = "rooms"
        ordering = ["city", "price_per_night"]

    def __str__(self):
        return f"{self.name} ({self.city}) — ₹{self.price_per_night}/night"

    @builtins.property
    def rating_pct(self):
        """Rating as a percentage (0-100) for the split-fill star widget."""
        if self.rating is None:
            return 0
        return float(self.rating) / 5 * 100

    @builtins.property
    def amenities_list(self):
        """Return amenities as a list."""
        if not self.amenities:
            return []
        return [a.strip() for a in self.amenities.split(",") if a.strip()]

    def calculate_price(self, check_in, check_out):
        """
        Calculate total price for the given dates, applying any RoomRate overrides.
        """
        from datetime import timedelta
        
        # Get all dynamic rates that overlap this booking
        rates = self.rates.filter(
            start_date__lt=check_out,
            end_date__gt=check_in
        )
        
        # Build a lookup for fast access
        rate_lookup = {}
        for r in rates:
            current = r.start_date
            while current <= r.end_date:
                rate_lookup[current] = r.price
                current += timedelta(days=1)
                
        total_price = 0
        current_date = check_in
        while current_date < check_out:
            # Use override if exists, else base price
            daily_price = rate_lookup.get(current_date, self.price_per_night)
            total_price += daily_price
            current_date += timedelta(days=1)
            
        return total_price


class RoomImage(models.Model):
    """
    Image for a hotel room. Supports multiple images per room
    with one marked as the primary/hero image.
    """
    objects = models.Manager()

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
    objects = models.Manager()

    # Type annotations for static typing / Pyrefly
    payments: models.Manager

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
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
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default='0.00',
        help_text="GST amount computed from PropertyTaxConfig at confirmation time.",
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
        help_text="Human-readable booking reference (e.g., TT-2026-00001).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "booking"
        verbose_name_plural = "bookings"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_out__gt=models.F("check_in")),
                name="check_out_after_check_in",
            ),
        ]

    def __str__(self):
        return f"Booking: {self.user.email} -> {self.room.name} ({self.check_in} to {self.check_out}) [{self.status}]"

    @builtins.property
    def num_nights(self):
        return (self.check_out - self.check_in).days

    @builtins.property
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

    def release_hold(self, reason="abandoned"):
        """
        Release an unpaid hold early, freeing the room immediately instead of
        waiting for the 10-minute timeout.

        Single source of truth for ending a PENDING hold — used by the explicit
        release endpoint (back-nav / refresh / modal dismiss) and the payment
        failure paths (signature mismatch, webhook payment.failed).

        reason:
            "payment_failed" → status becomes FAILED
            anything else    → status becomes EXPIRED (user abandoned the hold)

        Idempotent: a no-op (returns False) for any non-pending booking, so it is
        safe to call repeatedly and via navigator.sendBeacon.
        """
        if self.status != "pending":
            return False
        self.status = "failed" if reason == "payment_failed" else "expired"
        self.hold_expires_at = None
        self.save(update_fields=["status", "hold_expires_at"])
        return True

    def generate_booking_reference(self):
        """Generate a human-readable TT-{year}-{NNNNN} reference (e.g. TT-2026-00001).

        Called on booking confirmation. The number is a per-year sequence derived
        from the highest existing reference for the current year — the UUID primary
        key cannot supply a readable sequential number. ``booking_reference`` is
        unique; on the rare race where two confirmations pick the same number the
        insert fails and we retry with the next one. Idempotent: returns the
        existing reference if already set.
        """
        from django.db import IntegrityError, transaction

        if self.booking_reference:
            return self.booking_reference

        year = timezone.now().year
        prefix = f"TT-{year}-"
        for _ in range(5):
            last = (
                Booking.objects.filter(booking_reference__startswith=prefix)
                .order_by("-booking_reference")
                .first()
            )
            if last and last.booking_reference:
                try:
                    next_seq = int(last.booking_reference.rsplit("-", 1)[1]) + 1
                except ValueError:
                    next_seq = 1
            else:
                next_seq = 1
            self.booking_reference = f"{prefix}{next_seq:05d}"
            try:
                with transaction.atomic():
                    self.save(update_fields=["booking_reference"])
                return self.booking_reference
            except IntegrityError:
                self.booking_reference = None

        # Extremely unlikely fallback: guaranteed-unique, non-sequential.
        self.booking_reference = f"{prefix}{uuid.uuid4().hex[:6].upper()}"
        self.save(update_fields=["booking_reference"])
        return self.booking_reference

    def compute_tax(self):
        """Compute GST from PropertyTaxConfig and store in tax_amount. Returns amount."""
        from decimal import Decimal
        prop = self.room.property
        try:
            if prop is None:
                raise ValueError("Room has no property; cannot compute tax.")
            cfg = prop.tax_config
            nightly_rate = self.total_price / self.num_nights if self.num_nights else self.total_price
            rate = cfg.gst_rate_for(nightly_rate)
            self.tax_amount = (self.total_price * rate / Decimal('100')).quantize(Decimal('0.01'))
        except Exception:
            self.tax_amount = Decimal('0.00')
        self.save(update_fields=["tax_amount"])
        return self.tax_amount


class OTABlock(models.Model):
    """
    Represents a room block from an OTA (Online Travel Agency) or a manual block by an admin.
    """
    objects = models.Manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="ota_blocks")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True, default="OTA Block")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "OTA block"
        verbose_name_plural = "OTA blocks"
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="ota_end_date_after_start_date",
            ),
        ]

    def __str__(self):
        return f"Block for {self.room.name} ({self.start_date} to {self.end_date})"


class RoomRate(models.Model):
    """
    Dynamic pricing override for a specific room and date range.
    """
    objects = models.Manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="rates")
    start_date = models.DateField()
    end_date = models.DateField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Overridden price per night in INR.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "room rate"
        verbose_name_plural = "room rates"
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="rate_end_date_after_start_date",
            ),
        ]

    def __str__(self):
        return f"Rate for {self.room.name}: Rs.{self.price} ({self.start_date} to {self.end_date})"

