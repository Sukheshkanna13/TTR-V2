"""
Admin configuration for rooms and bookings with django-unfold.

Provides:
- Rich booking management with status, city, and date filters
- Searchable by booking reference and user email
- Custom dashboard with live stats (today's count, revenue, check-ins)
- Inline image upload for rooms
"""

from datetime import date

from django.contrib import admin
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from .models import Booking, Property, Room, RoomImage

@admin.register(Property)
class PropertyAdmin(ModelAdmin):
    list_display = ("name", "city", "whatsapp_number", "is_active", "created_at")
    list_filter = ("city", "is_active")
    search_fields = ("name", "city", "whatsapp_number")
    list_editable = ("is_active",)
    list_per_page = 25

class RoomImageInline(TabularInline):
    """Inline for uploading images directly from the Room admin page."""

    model = RoomImage
    extra = 1  # Show 1 empty upload slot by default
    fields = ("image", "caption", "is_primary", "order", "image_preview")
    readonly_fields = ("image_preview",)
    ordering = ("order",)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 80px; border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.15);" />',
                obj.image.url,
            )
        return "No image"

    image_preview.short_description = "Preview"


@admin.register(Room)
class RoomAdmin(ModelAdmin):
    list_display = (
        "name",
        "property",
        "city",
        "room_type",
        "price_per_night",
        "capacity",
        "image_count",
        "is_active",
    )
    list_filter = ("property", "city", "room_type", "is_active")
    search_fields = ("name", "city", "description", "property__name")
    list_editable = ("is_active", "price_per_night")
    list_per_page = 25
    inlines = [RoomImageInline]

    fieldsets = (
        ("Room Info", {
            "fields": ("property", "name", "city", "room_type", "description"),
        }),
        ("Pricing & Capacity", {
            "fields": ("price_per_night", "capacity"),
        }),
        ("Amenities", {
            "fields": ("amenities",),
        }),
        ("Status", {
            "fields": ("is_active",),
        }),
    )

    @admin.display(description="Images")
    def image_count(self, obj):
        count = obj.images.count()
        if count == 0:
            return format_html('<span style="color: #ef4444;">0 ⚠</span>')
        return count

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("property").prefetch_related("images")


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    list_display = (
        "booking_reference",
        "room",
        "get_user_email",
        "get_city",
        "check_in",
        "check_out",
        "guests",
        "total_price",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "room__city",
        "check_in",
        "created_at",
    )
    search_fields = (
        "booking_reference",
        "user__email",
        "user__full_name",
        "room__name",
        "razorpay_order_id",
    )
    readonly_fields = (
        "id",
        "created_at",
        "hold_expires_at",
        "razorpay_order_id",
        "booking_reference",
    )
    list_per_page = 25
    date_hierarchy = "check_in"

    fieldsets = (
        ("Booking Info", {
            "fields": (
                "id",
                "booking_reference",
                "status",
            ),
        }),
        ("Guest", {
            "fields": ("user", "guests"),
        }),
        ("Room & Dates", {
            "fields": ("room", "check_in", "check_out"),
        }),
        ("Payment", {
            "fields": ("total_price", "razorpay_order_id"),
        }),
        ("Hold", {
            "fields": ("hold_expires_at",),
        }),
        ("Timestamps", {
            "fields": ("created_at",),
        }),
    )

    @admin.display(description="User Email")
    def get_user_email(self, obj):
        return obj.user.email

    @admin.display(description="City")
    def get_city(self, obj):
        return obj.room.city

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("room", "user")
