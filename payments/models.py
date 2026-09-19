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
        ("refunded", "Refunded"),
    ]

    METHOD_RAZORPAY = "razorpay"
    METHOD_CASH = "cash"
    METHOD_CARD_POS = "card_pos"
    METHOD_UPI_DIRECT = "upi_direct"
    METHOD_BANK_TRANSFER = "bank_transfer"
    METHOD_PAY_AT_CHECKOUT = "pay_at_checkout"

    METHOD_CHOICES = [
        (METHOD_RAZORPAY, "Razorpay Online"),
        (METHOD_CASH, "Cash"),
        (METHOD_CARD_POS, "Card POS Swipe"),
        (METHOD_UPI_DIRECT, "Direct UPI Transfer"),
        (METHOD_BANK_TRANSFER, "Direct Bank Transfer"),
        (METHOD_PAY_AT_CHECKOUT, "Pay at Checkout"),
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
    payment_method = models.CharField(
        max_length=25,
        choices=METHOD_CHOICES,
        default=METHOD_RAZORPAY,
        db_index=True,
    )
    razorpay_order_id = models.CharField(max_length=100, blank=True, default="")
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
    refund_id = models.CharField(max_length=100, blank=True, default="")
    refund_status = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "payment"
        verbose_name_plural = "payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.razorpay_order_id} - {self.status} - Rs.{self.amount}"


class ProcessedWebhookEvent(models.Model):
    """
    Tracks processed webhook event IDs across payment gateways and channel managers
    to guarantee idempotency and prevent duplicate execution / replay attacks.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=50, db_index=True)
    event_id = models.CharField(max_length=150, db_index=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "processed webhook event"
        verbose_name_plural = "processed webhook events"
        ordering = ["-processed_at"]
        constraints = [
            models.UniqueConstraint(fields=["source", "event_id"], name="unique_webhook_event")
        ]

    def __str__(self):
        return f"Webhook [{self.source}] {self.event_id} at {self.processed_at}"
