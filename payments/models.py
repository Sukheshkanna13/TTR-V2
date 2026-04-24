"""
Payment model — stores every Razorpay transaction for audit & reference.
"""

import uuid

from django.db import models

from rooms.models import Booking


class Payment(models.Model):
    """
    Records a Razorpay payment attempt linked to a booking.
    """

    STATUS_CHOICES = [
        ("created", "Created"),
        ("captured", "Captured"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    razorpay_order_id = models.CharField(max_length=100)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, default="")
    razorpay_signature = models.CharField(max_length=256, blank=True, default="")
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount in INR.",
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="created",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "payment"
        verbose_name_plural = "payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.razorpay_order_id} - {self.status} - Rs.{self.amount}"
