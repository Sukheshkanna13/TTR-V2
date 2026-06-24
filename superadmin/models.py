import uuid
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Immutable record of every significant admin action."""
    ACTION_CHOICES = [
        ('EMPLOYEE_CREATED', 'Employee Created'),
        ('EMPLOYEE_UPDATED', 'Employee Updated'),
        ('EMPLOYEE_LOCKED', 'Employee Locked'),
        ('EMPLOYEE_UNLOCKED', 'Employee Unlocked'),
        ('EMPLOYEE_REVOKED', 'Employee Revoked'),
        ('EMPLOYEE_DELETED', 'Employee Deleted'),
        ('PASSWORD_RESET', 'Password Reset'),
        ('BOOKING_CANCELLED', 'Booking Cancelled'),
        ('BOOKING_COMPLETED', 'Booking Completed'),
        ('PROPERTY_CREATED', 'Property Created'),
        ('PROPERTY_UPDATED', 'Property Updated'),
        ('ROOM_CREATED', 'Room Created'),
        ('ROOM_UPDATED', 'Room Updated'),
        ('ROOM_DELETED', 'Room Deleted'),
        ('ROOM_STATUS_UPDATED', 'Room Status Updated'),
        ('ROOM_IMAGE_UPLOADED', 'Room Image Uploaded'),
        ('ROOM_IMAGE_DELETED', 'Room Image Deleted'),
        ('TAX_CONFIG_UPDATED', 'Tax Config Updated'),
        ('LOYALTY_CONFIG_UPDATED', 'Loyalty Config Updated'),
        ('LOYALTY_CREDIT', 'Loyalty Credit'),
        ('LOYALTY_DEBIT', 'Loyalty Debit'),
        ('PROPERTY_ASSIGNMENT_CHANGED', 'Property Assignment Changed'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_actions',
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_events',
    )
    detail = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.actor} → {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"


class PropertyTaxConfig(models.Model):
    """Threshold-based GST config per property. Never hardcode rates."""
    property = models.OneToOneField(
        'rooms.Property',
        on_delete=models.CASCADE,
        related_name='tax_config',
    )
    threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default='7500.00',
        help_text="Nightly rate threshold (₹). Below → low_rate_pct, at/above → high_rate_pct.",
    )
    low_rate_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default='12.00',
        help_text="GST % for rooms priced below the threshold.",
    )
    high_rate_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default='18.00',
        help_text="GST % for rooms priced at or above the threshold.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Property Tax Config"

    def __str__(self):
        return f"Tax config — {self.property} (threshold ₹{self.threshold})"

    def gst_rate_for(self, nightly_rate):
        """Return the applicable GST rate (Decimal) for a given nightly rate."""
        from decimal import Decimal
        if Decimal(str(nightly_rate)) >= self.threshold:
            return self.high_rate_pct
        return self.low_rate_pct
