from django.contrib import admin
from django.utils import timezone
from .models import Attraction, AttractionPhoto, Cause, Activity
from core.ota.models import (
    ChannexProperty,
    ChannexRoomType,
    ChannexRatePlan,
    ARIChange,
)


class AttractionPhotoInline(admin.TabularInline):
    model = AttractionPhoto
    extra = 1


@admin.register(Attraction)
class AttractionAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'category', 'is_visible', 'sort_order']
    list_filter = ['city', 'category', 'is_visible']
    search_fields = ['name', 'city', 'description']
    inlines = [AttractionPhotoInline]


@admin.register(Cause)
class CauseAdmin(admin.ModelAdmin):
    list_display = ['title', 'location', 'target_amount', 'raised_amount', 'is_active', 'sort_order']
    list_filter = ['location', 'is_active']
    search_fields = ['title', 'location', 'description']


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'price', 'is_active', 'sort_order']
    list_filter = ['category', 'is_active']
    search_fields = ['title', 'category', 'description']


# ---------------------------------------------------------------------------
# Channex OTA mapping + outbox admin
# ---------------------------------------------------------------------------

class ChannexRoomTypeInline(admin.TabularInline):
    """Inline for managing room-type mappings under a ChannexProperty."""
    model = ChannexRoomType
    extra = 0
    fields = ("room_type", "channex_room_type_id")
    show_change_link = True


class ChannexRatePlanInline(admin.TabularInline):
    """Inline for managing rate-plan mappings under a ChannexRoomType."""
    model = ChannexRatePlan
    extra = 0
    fields = ("name", "channex_rate_plan_id", "is_default")


@admin.register(ChannexProperty)
class ChannexPropertyAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "channex_property_id",
        "currency",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "currency")
    search_fields = ("property__name", "channex_property_id")
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("property",)
    inlines = [ChannexRoomTypeInline]


@admin.register(ChannexRoomType)
class ChannexRoomTypeAdmin(admin.ModelAdmin):
    list_display = (
        "property_mapping",
        "room_type",
        "channex_room_type_id",
        "updated_at",
    )
    list_filter = ("room_type",)
    search_fields = (
        "property_mapping__property__name",
        "channex_room_type_id",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("property_mapping__property",)
    inlines = [ChannexRatePlanInline]


@admin.register(ChannexRatePlan)
class ChannexRatePlanAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "room_type_mapping",
        "channex_rate_plan_id",
        "is_default",
        "updated_at",
    )
    list_filter = ("is_default",)
    search_fields = (
        "name",
        "channex_rate_plan_id",
        "room_type_mapping__property_mapping__property__name",
    )
    readonly_fields = ("id", "created_at", "updated_at")
    list_select_related = ("room_type_mapping__property_mapping__property",)


@admin.register(ARIChange)
class ARIChangeAdmin(admin.ModelAdmin):
    """Read-only audit view of the outbound ARI outbox."""
    list_display = (
        "property_mapping",
        "change_type",
        "room_type",
        "date_from",
        "date_to",
        "status",
        "retry_count",
        "next_retry_at",
        "created_at",
    )
    list_filter = ("status", "change_type", "room_type", "property_mapping")
    search_fields = ("channex_task_id", "error_detail")
    list_select_related = ("property_mapping__property",)
    readonly_fields = (
        "id",
        "property_mapping",
        "change_type",
        "room_type",
        "date_from",
        "date_to",
        "status",
        "retry_count",
        "next_retry_at",
        "channex_task_id",
        "error_detail",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
    actions = ("requeue_changes",)

    @admin.action(description="Requeue selected changes (reset retries, push on next run)")
    def requeue_changes(self, request, queryset):
        now = timezone.now()
        count = queryset.update(
            status=ARIChange.STATUS_PENDING,
            retry_count=0,
            next_retry_at=now,
            error_detail="",
            updated_at=now,
        )
        self.message_user(request, f"Requeued {count} change(s); the outbox worker picks them up within a minute.")

    def has_add_permission(self, request):
        """Outbox rows are created by code only, never manually."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent manual deletion — outbox integrity matters."""
        return False


