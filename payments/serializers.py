"""
Serializers for payment endpoints.
"""

from rest_framework import serializers


class CreateOrderSerializer(serializers.Serializer):
    """Validates the create-order request."""
    booking_id = serializers.UUIDField(
        error_messages={"required": "Booking ID is required."},
    )


class VerifyPaymentSerializer(serializers.Serializer):
    """
    Validates the payment verification data from Razorpay checkout.
    These 3 values come from the browser after Razorpay popup completes.
    """
    razorpay_order_id = serializers.CharField(
        error_messages={"required": "Order ID is required."},
    )
    razorpay_payment_id = serializers.CharField(
        error_messages={"required": "Payment ID is required."},
    )
    razorpay_signature = serializers.CharField(
        error_messages={"required": "Signature is required."},
    )
