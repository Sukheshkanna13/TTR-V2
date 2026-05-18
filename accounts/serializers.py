"""
DRF Serializers for the accounts app.

3-Step Registration Flow:
  Step 1 — InitiateRegistrationSerializer  : email + name + phone → sends OTP, no User created
  Step 2 — VerifyOTPSerializer             : email + otp → marks email verified
  Step 3 — SetPasswordSerializer           : email + password → creates User, logs in
"""

import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


# =============================================================================
# STEP 1 — Initiate registration (no password, no user created)
# =============================================================================

class InitiateRegistrationSerializer(serializers.Serializer):
    """
    Validates the first step of registration: name, email, phone.
    No password at this stage. No User row is created.
    """

    full_name = serializers.CharField(
        max_length=150,
        error_messages={"required": "Full name is required.", "blank": "Full name cannot be blank."},
    )
    email = serializers.EmailField(
        error_messages={"required": "Email is required.", "invalid": "Enter a valid email address."},
    )
    phone = serializers.CharField(
        max_length=15,
        error_messages={"required": "Phone number is required.", "blank": "Phone number cannot be blank."},
    )

    def validate_email(self, value):
        email = value.lower().strip()
        # Block if a fully-active user already exists
        if User.objects.filter(email=email, is_active=True).exists():
            raise serializers.ValidationError("An account with this email already exists and is active. Please log in.")
        return email

    def validate_phone(self, value):
        phone = value.strip()
        if not re.match(r"^\+?[\d\-\s]{7,15}$", phone):
            raise serializers.ValidationError(
                "Enter a valid phone number (7-15 digits, optionally starting with +)."
            )
        return re.sub(r"[^\d+]", "", phone)


# =============================================================================
# STEP 2 — Verify OTP (email + code only)
# =============================================================================

class VerifyOTPSerializer(serializers.Serializer):
    """Validates OTP verification input."""

    email = serializers.EmailField(
        error_messages={"required": "Email is required.", "invalid": "Enter a valid email address."},
    )
    otp = serializers.CharField(
        max_length=6,
        min_length=6,
        error_messages={
            "required": "OTP is required.",
            "min_length": "OTP must be exactly 6 digits.",
            "max_length": "OTP must be exactly 6 digits.",
        },
    )

    def validate_email(self, value):
        return value.lower().strip()

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        return value


# =============================================================================
# STEP 3 — Set password and complete registration
# =============================================================================

class SetPasswordSerializer(serializers.Serializer):
    """
    Validates the final step: email + password.
    Only allowed if the PendingRegistration is verified.
    """

    email = serializers.EmailField(
        error_messages={"required": "Email is required.", "invalid": "Enter a valid email address."},
    )
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={"required": "Password is required.", "min_length": "Password must be at least 8 characters."},
    )

    def validate_email(self, value):
        return value.lower().strip()

    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", value):
            raise serializers.ValidationError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        return value


# =============================================================================
# OTHER — Resend OTP, Login, Me
# =============================================================================

class ResendOTPSerializer(serializers.Serializer):
    """Validates resend OTP input."""

    email = serializers.EmailField(
        error_messages={"required": "Email is required.", "invalid": "Enter a valid email address."},
    )

    def validate_email(self, value):
        return value.lower().strip()


class LoginSerializer(serializers.Serializer):
    """Validates login input."""

    email = serializers.EmailField(
        error_messages={"required": "Email is required.", "invalid": "Enter a valid email address."},
    )
    password = serializers.CharField(
        write_only=True,
        error_messages={"required": "Password is required."},
    )

    def validate_email(self, value):
        return value.lower().strip()


class UserSerializer(serializers.ModelSerializer):
    """Serializes user data for API responses."""

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "is_active", "is_staff", "date_joined"]
        read_only_fields = fields


class EmployeeCreationSerializer(serializers.Serializer):
    """Validates employee creation input."""

    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15)
    role = serializers.ChoiceField(choices=[("employee_admin", "Employee Admin"), ("super_admin", "Super Admin")])
    fin_level = serializers.ChoiceField(choices=[("A", "A"), ("B", "B"), ("C", "C")], required=False, allow_null=True)
    assigned_properties = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email


# Keep old name as alias for backward compat with any existing code references
RegisterSerializer = InitiateRegistrationSerializer
