import uuid
from django.conf import settings
from django.db import models


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
