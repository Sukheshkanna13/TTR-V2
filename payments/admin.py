"""
Admin configuration for payments.
"""

from django.contrib import admin

from .models import Payment, ProcessedWebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "razorpay_order_id",
        "razorpay_payment_id",
        "payment_method",
        "amount",
        "status",
        "refund_status",
        "get_booking_ref",
        "get_user_email",
        "created_at",
    )
    list_filter = ("status", "payment_method", "refund_status", "created_at")
    search_fields = (
        "razorpay_order_id",
        "razorpay_payment_id",
        "refund_id",
        "booking__booking_reference",
        "booking__user__email",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    list_per_page = 25

    fieldsets = (
        ("Payment Info", {
            "fields": ("id", "status", "payment_method", "amount"),
        }),
        ("Razorpay Details", {
            "fields": (
                "razorpay_order_id",
                "razorpay_payment_id",
                "razorpay_signature",
            ),
        }),
        ("Refund Details", {
            "fields": (
                "refund_id",
                "refund_status",
            ),
        }),
        ("Booking", {
            "fields": ("booking",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    @admin.display(description="Booking Ref")
    def get_booking_ref(self, obj):
        return obj.booking.booking_reference or str(obj.booking.id)[:8]

    @admin.display(description="User")
    def get_user_email(self, obj):
        return obj.booking.user.email

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "booking", "booking__user"
        )


@admin.register(ProcessedWebhookEvent)
class ProcessedWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("source", "event_id", "processed_at")
    list_filter = ("source", "processed_at")
    search_fields = ("event_id", "source")
    readonly_fields = ("id", "processed_at")
    list_per_page = 50
