"""
Admin configuration for the accounts app with django-unfold.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin

from .models import LoginAttempt, OTP

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    """Custom admin view for the User model."""

    list_display = ("email", "full_name", "phone", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "date_joined")
    search_fields = ("email", "full_name", "phone")
    ordering = ("-date_joined",)
    list_per_page = 25

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("full_name", "phone")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "phone", "password1", "password2"),
            },
        ),
    )


@admin.register(OTP)
class OTPAdmin(ModelAdmin):
    """Admin view for OTP records."""

    list_display = ("email", "code", "attempts", "created_at", "expires_at", "is_expired_display")
    list_filter = ("created_at",)
    search_fields = ("email",)
    readonly_fields = ("id", "created_at")

    @admin.display(boolean=True, description="Expired?")
    def is_expired_display(self, obj):
        return obj.is_expired


@admin.register(LoginAttempt)
class LoginAttemptAdmin(ModelAdmin):
    """Admin view for login attempt tracking."""

    list_display = ("email", "attempts", "locked_until", "last_attempt_at", "is_locked_display")
    search_fields = ("email",)
    readonly_fields = ("last_attempt_at",)

    @admin.display(boolean=True, description="Locked?")
    def is_locked_display(self, obj):
        return obj.is_locked
