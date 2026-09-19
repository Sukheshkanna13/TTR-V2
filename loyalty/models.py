import uuid
import builtins
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone


class LoyaltyConfig(models.Model):
    """Per-property loyalty point rules. Never hardcode — always read from here."""
    property = models.OneToOneField(
        'rooms.Property',
        on_delete=models.CASCADE,
        related_name='loyalty_config',
    )
    first_booking_pts = models.PositiveIntegerField(
        default=200,
        help_text="Points for a guest's very first confirmed booking.",
    )
    pts_per_night = models.PositiveIntegerField(
        default=100,
        help_text="Points per night for all bookings after the first.",
    )
    monthly_repeat_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default='1.50',
        help_text="Multiplier when guest has ≥2 confirmed bookings in the same calendar month.",
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Loyalty Config"

    def __str__(self):
        return f"LoyaltyConfig — {self.property}"


class LoyaltyTier(models.Model):
    """DB-driven tiers — Super Admin controls names, thresholds, discounts."""
    name = models.CharField(max_length=50, unique=True)
    min_pts = models.PositiveIntegerField(help_text="Minimum points to reach this tier.")
    discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default='0.00',
        help_text="Discount percentage for guests in this tier.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'min_pts']

    def __str__(self):
        return f"{self.name} (≥{self.min_pts} pts, {self.discount_pct}% off)"


class CampaignRule(models.Model):
    """Date-range multiplier campaigns per property (or platform-wide)."""
    property = models.ForeignKey(
        'rooms.Property',
        on_delete=models.CASCADE,
        related_name='campaign_rules',
        null=True, blank=True,
        help_text="Leave blank to apply across all properties.",
    )
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default='1.00',
        help_text="Applied to base points for bookings whose check-in falls in this range.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.start_date}–{self.end_date}, ×{self.multiplier})"


class LoyaltyLedger(models.Model):
    """Immutable audit trail of every point transaction."""
    REASON_CHOICES = [
        ('BOOKING_CONFIRMED', 'Booking Confirmed'),
        ('TIER_UPGRADE', 'Tier Upgrade Bonus'),
        ('ADMIN_ADJUSTMENT', 'Admin Adjustment'),
        ('COUPON_REDEMPTION', 'Coupon Redemption'),
        ('REFUND_DEDUCTION', 'Refund Deduction'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='loyalty_ledger',
    )
    booking = models.ForeignKey(
        'rooms.Booking',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='loyalty_entries',
    )
    delta = models.IntegerField(help_text="Positive = earned, negative = redeemed/deducted.")
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.delta >= 0 else ''
        return f"{self.user.email}: {sign}{self.delta} pts ({self.reason})"


class CouponRedemptionRule(models.Model):
    """
    Super Admin configurable rules converting loyalty points into discount coupons.
    e.g. 100 points = ₹250 off voucher, min booking ₹2000, 30 days validity.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(
        'rooms.Property',
        on_delete=models.CASCADE,
        related_name='redemption_rules',
        null=True, blank=True,
        help_text="Leave blank for platform-wide availability across all properties.",
    )
    name = models.CharField(max_length=100, help_text="e.g. ₹250 Off Stay Voucher")
    points_cost = models.PositiveIntegerField(help_text="Points required to redeem this coupon")
    discount_type = models.CharField(
        max_length=20,
        choices=[('fixed', 'Fixed Amount (₹)'), ('percentage', 'Percentage (%)')],
        default='fixed',
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Discount in ₹ or %")
    min_booking_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default='0.00',
        help_text="Minimum booking total required to use this coupon.",
    )
    max_discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Max discount cap for percentage vouchers.",
    )
    validity_days = models.PositiveIntegerField(
        default=30,
        help_text="Number of days the coupon remains valid after redemption.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['points_cost', 'discount_value']
        verbose_name = "Coupon Redemption Rule"
        verbose_name_plural = "Coupon Redemption Rules"

    def __str__(self):
        return f"{self.name} ({self.points_cost} pts -> {self.discount_display})"

    @builtins.property
    def discount_display(self):
        if self.discount_type == 'percentage':
            return f"{self.discount_value}% off"
        return f"₹{self.discount_value} off"


class Coupon(models.Model):
    """
    Discount coupon issued to a guest via points redemption or created by admin as a promo.
    """
    STATUS_ACTIVE = "active"
    STATUS_APPLIED = "applied"
    STATUS_REDEEMED = "redeemed"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_APPLIED, "Applied to Hold"),
        (STATUS_REDEEMED, "Redeemed"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='coupons',
        null=True, blank=True,
        help_text="Owner of the coupon. Null for general public promo codes.",
    )
    redemption_rule = models.ForeignKey(
        CouponRedemptionRule,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='issued_coupons',
    )
    discount_type = models.CharField(
        max_length=20,
        choices=[('fixed', 'Fixed Amount (₹)'), ('percentage', 'Percentage (%)')],
        default='fixed',
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_booking_amount = models.DecimalField(max_digits=10, decimal_places=2, default='0.00')
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Coupon"
        verbose_name_plural = "Coupons"

    def __str__(self):
        return f"{self.code} ({self.discount_display}) [{self.status}]"

    @builtins.property
    def discount_display(self):
        if self.discount_type == 'percentage':
            return f"{self.discount_value}% off"
        return f"₹{self.discount_value} off"

    @builtins.property
    def is_expired(self):
        return timezone.now() > self.valid_until

    def calculate_discount(self, booking_amount):
        """Calculates discount amount in INR for the given booking total price."""
        from decimal import Decimal
        amt = Decimal(str(booking_amount))
        if amt < self.min_booking_amount:
            return Decimal('0.00')

        if self.discount_type == 'percentage':
            disc = (amt * self.discount_value / Decimal('100')).quantize(Decimal('0.01'))
            if self.max_discount_amount:
                disc = min(disc, self.max_discount_amount)
            return min(disc, amt)
        else:
            return min(self.discount_value, amt)

    def validate_for_booking(self, booking, user=None):
        """
        Validates whether this coupon can be applied to the given booking.
        Returns (is_valid: bool, reason: str).
        """
        now = timezone.now()
        if self.status != self.STATUS_ACTIVE:
            if self.status == self.STATUS_REDEEMED:
                return False, "This coupon has already been redeemed."
            return False, f"This coupon is {self.status}."

        if now < self.valid_from:
            return False, "This coupon is not yet active."
        if now > self.valid_until:
            return False, "This coupon has expired."

        # User-bound check
        if self.user:
            check_user = user or getattr(booking, "user", None)
            if not check_user or check_user.id != self.user_id:
                return False, "This coupon belongs to a different guest account."

        # Min booking amount
        if booking.total_price < self.min_booking_amount:
            return False, f"Booking amount must be at least ₹{self.min_booking_amount} to use this coupon."

        # Property scope check if created from property-specific rule
        if self.redemption_rule and self.redemption_rule.property_id:
            if booking.room.property_id != self.redemption_rule.property_id:
                return False, f"This coupon is only valid at {self.redemption_rule.property.name}."

        return True, ""
