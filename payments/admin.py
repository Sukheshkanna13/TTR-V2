"""
Admin configuration for payments.
"""

from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "razorpay_order_id",
        "razorpay_payment_id",
        "amount",
        "status",
        "get_booking_ref",
        "get_user_email",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "razorpay_order_id",
        "razorpay_payment_id",
        "booking__booking_reference",
        "booking__user__email",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    list_per_page = 25

    fieldsets = (
        ("Payment Info", {
            "fields": ("id", "status", "amount"),
        }),
        ("Razorpay Details", {
            "fields": (
                "razorpay_order_id",
                "razorpay_payment_id",
                "razorpay_signature",
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
