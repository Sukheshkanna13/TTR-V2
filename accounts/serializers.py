"""
DRF Serializers for the accounts app.
Handles validation for registration, OTP, and login flows.
"""

import re

from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    """
    Validates user registration input.
    - Checks for duplicate emails
    - Validates phone format
    - Enforces password strength rules
    """

    full_name = serializers.CharField(
        max_length=150,
        error_messages={
            "required": "Full name is required.",
            "blank": "Full name cannot be blank.",
        },
    )
    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "invalid": "Enter a valid email address.",
        },
    )
    phone = serializers.CharField(
        max_length=15,
        error_messages={
            "required": "Phone number is required.",
            "blank": "Phone number cannot be blank.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "required": "Password is required.",
            "min_length": "Password must be at least 8 characters long.",
        },
    )

    def validate_email(self, value):
        """Check that the email is not already registered."""
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return email

    def validate_phone(self, value):
        """
        Validate phone number format.
        Accepts formats like: +1234567890, +91-9876543210, 1234567890
        """
        phone = value.strip()
        pattern = r"^\+?[\d\-\s]{7,15}$"
        if not re.match(pattern, phone):
            raise serializers.ValidationError(
                "Enter a valid phone number (7-15 digits, optionally starting with +)."
            )
        # Remove all non-digit characters except leading +
        cleaned = re.sub(r"[^\d+]", "", phone)
        return cleaned

    def validate_password(self, value):
        """
        Enforce password strength:
        - At least 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        """
        if len(value) < 8:
            raise serializers.ValidationError(
                "Password must be at least 8 characters long."
            )
        if not re.search(r"[A-Z]", value):
            raise serializers.ValidationError(
                "Password must contain at least one uppercase letter."
            )
        if not re.search(r"[a-z]", value):
            raise serializers.ValidationError(
                "Password must contain at least one lowercase letter."
            )
        if not re.search(r"\d", value):
            raise serializers.ValidationError(
                "Password must contain at least one digit."
            )
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", value):
            raise serializers.ValidationError(
                "Password must contain at least one special character."
            )
        return value

    def create(self, validated_data):
        """
        Create a new user with is_active=False.
        Password is hashed via bcrypt (configured in settings).
        """
        user = User.objects.create_user(
            email=validated_data["email"],
            full_name=validated_data["full_name"],
            phone=validated_data["phone"],
            password=validated_data["password"],
        )
        return user


class VerifyOTPSerializer(serializers.Serializer):
    """Validates OTP verification input."""

    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "invalid": "Enter a valid email address.",
        },
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


class ResendOTPSerializer(serializers.Serializer):
    """Validates resend OTP input."""

    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "invalid": "Enter a valid email address.",
        },
    )

    def validate_email(self, value):
        return value.lower().strip()


class LoginSerializer(serializers.Serializer):
    """Validates login input."""

    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "invalid": "Enter a valid email address.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "Password is required.",
        },
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
    """
    Validates employee creation input.
    """
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15)
    role = serializers.ChoiceField(choices=[('employee', 'Employee'), ('super_admin', 'Super Admin')])
    fin_level = serializers.ChoiceField(choices=[('A', 'A'), ('B', 'B'), ('C', 'C')], required=False, allow_null=True)
    assigned_properties = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=True
    )

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email
