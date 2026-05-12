"""
Admin configuration for rooms and bookings.

Provides:
- Booking management with status, city, and date filters
- Searchable by booking reference and user email
- Inline image upload for rooms
- OTABlock and RoomRate management
"""

from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import Booking, OTABlock, Property, Room, RoomImage, RoomRate


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "whatsapp_number", "is_active", "created_at")
    list_filter = ("city", "is_active")
    search_fields = ("name", "city", "whatsapp_number")
    list_editable = ("is_active",)
    list_per_page = 25


class RoomImageInline(admin.TabularInline):
    """Inline for uploading images directly from the Room admin page."""

    model = RoomImage
    extra = 1
    fields = ("image", "caption", "is_primary", "order", "image_preview")
    readonly_fields = ("image_preview",)
    ordering = ("order",)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 80px; border-radius: 6px;" />',
                obj.image.url,
            )
        return "No image"

    image_preview.short_description = "Preview"


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "property",
        "city",
        "room_type",
        "price_per_night",
        "capacity",
        "operational_status",
        "image_count",
        "is_active",
    )
    list_filter = ("property", "city", "room_type", "is_active", "operational_status")
    search_fields = ("name", "city", "description", "property__name")
    list_editable = ("is_active", "price_per_night", "operational_status")
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
            "fields": ("is_active", "operational_status"),
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
class BookingAdmin(admin.ModelAdmin):
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

    @admin.display(description="User Email")
    def get_user_email(self, obj):
        return obj.user.email

    @admin.display(description="City")
    def get_city(self, obj):
        return obj.room.city

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("room", "user")


@admin.register(OTABlock)
class OTABlockAdmin(admin.ModelAdmin):
    list_display = ("room", "start_date", "end_date", "reason", "created_at")
    list_filter = ("room__property", "room__city")
    search_fields = ("room__name", "reason")
    list_per_page = 25


@admin.register(RoomRate)
class RoomRateAdmin(admin.ModelAdmin):
    list_display = ("room", "start_date", "end_date", "price", "created_at")
    list_filter = ("room__property", "room__city")
    search_fields = ("room__name",)
    list_per_page = 25
