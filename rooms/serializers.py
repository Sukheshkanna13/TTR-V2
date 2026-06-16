"""
Serializers for rooms and bookings.
"""

from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Booking, Room, RoomImage

User = get_user_model()


class RoomImageSerializer(serializers.ModelSerializer):
    """Serializes room image data."""

    image_url = serializers.SerializerMethodField()

    class Meta:
        model = RoomImage
        fields = ["id", "image_url", "caption", "is_primary", "order"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        elif obj.image:
            return obj.image.url
        return None


class RoomSerializer(serializers.ModelSerializer):
    """Serializes room data for search results."""

    amenities_list = serializers.ReadOnlyField()
    images = RoomImageSerializer(many=True, read_only=True)
    primary_image = serializers.SerializerMethodField()
    property_rating = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            "id",
            "name",
            "city",
            "room_type",
            "price_per_night",
            "capacity",
            "amenities",
            "amenities_list",
            "description",
            "images",
            "primary_image",
            "dynamic_total_price",
            "property_rating",
            "property_name",
        ]

    def get_property_rating(self, obj):
        rating = getattr(obj.property, "rating", None)
        return float(rating) if rating is not None else None

    def get_property_name(self, obj):
        return getattr(obj.property, "name", "")

    dynamic_total_price = serializers.SerializerMethodField()

    def get_dynamic_total_price(self, obj):
        check_in = self.context.get("check_in")
        check_out = self.context.get("check_out")
        if check_in and check_out:
            return str(obj.calculate_price(check_in, check_out))
        return None

    def get_primary_image(self, obj):
        """Return the URL of the primary image, or the first image, or None."""
        request = self.context.get("request")
        primary = obj.images.filter(is_primary=True).first()
        if not primary:
            primary = obj.images.first()
        if primary and primary.image:
            if request:
                return request.build_absolute_uri(primary.image.url)
            return primary.image.url
        return None


class SearchSerializer(serializers.Serializer):
    """
    Validates the room search form input.
    """

    city = serializers.CharField(
        max_length=100,
        required=False,
        error_messages={"required": "City is required."},
    )
    property_id = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    check_in = serializers.DateField(
        error_messages={
            "required": "Check-in date is required.",
            "invalid": "Enter a valid date (YYYY-MM-DD).",
        },
    )
    check_out = serializers.DateField(
        error_messages={
            "required": "Check-out date is required.",
            "invalid": "Enter a valid date (YYYY-MM-DD).",
        },
    )
    # guests is optional — defaults to 1 if missing or 0; never block the request over a missing count
    guests = serializers.IntegerField(
        required=False,
        default=1,
        min_value=0,
        error_messages={"min_value": "Guests cannot be negative."},
    )

    # Optional filters
    room_type = serializers.ChoiceField(
        choices=Room.ROOM_TYPE_CHOICES,
        required=False,
    )
    min_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
    )
    max_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
    )
    sort = serializers.ChoiceField(
        choices=[("price_asc", "Price: Low to High"), ("price_desc", "Price: High to Low")],
        required=False,
    )

    def validate_check_in(self, value):
        if value < date.today():
            raise serializers.ValidationError("Check-in date cannot be in the past.")
        return value

    def validate(self, data):
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        if check_in and check_out and check_out <= check_in:
            raise serializers.ValidationError(
                {"check_out": "Check-out date must be after check-in date."}
            )
        # guests=0 means "any" — normalise to 1 so capacity filter still makes sense
        if data.get("guests", 1) < 1:
            data["guests"] = 1
        return data


class HoldRoomSerializer(serializers.Serializer):
    """
    Validates the hold/booking request.
    """

    room_id = serializers.UUIDField(
        error_messages={"required": "Room ID is required."},
    )
    check_in = serializers.DateField(
        error_messages={
            "required": "Check-in date is required.",
            "invalid": "Enter a valid date (YYYY-MM-DD).",
        },
    )
    check_out = serializers.DateField(
        error_messages={
            "required": "Check-out date is required.",
            "invalid": "Enter a valid date (YYYY-MM-DD).",
        },
    )
    guests = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": "Number of guests is required.",
            "min_value": "At least 1 guest is required.",
        },
    )

    def validate_check_in(self, value):
        if value < date.today():
            raise serializers.ValidationError("Check-in date cannot be in the past.")
        return value

    def validate(self, data):
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        if check_in and check_out and check_out <= check_in:
            raise serializers.ValidationError(
                {"check_out": "Check-out date must be after check-in date."}
            )
        return data


class BookingSerializer(serializers.ModelSerializer):
    """Serializes booking data for API responses."""

    room = RoomSerializer(read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    num_nights = serializers.ReadOnlyField()
    is_hold_expired = serializers.ReadOnlyField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "room",
            "user_email",
            "check_in",
            "check_out",
            "guests",
            "num_nights",
            "total_price",
            "status",
            "hold_expires_at",
            "is_hold_expired",
            "razorpay_order_id",
            "booking_reference",
            "created_at",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        
        # Expose pending as HELD in API to match spec terminology
        if data.get("status") == "pending":
            data["status"] = "HELD"
        
        if request and request.user.is_authenticated:
            user = request.user
            # Guests see their own price. Employees with Level A/B see prices.
            if user == instance.user:
                return data
                
            if hasattr(user, 'userprofile') and user.userprofile.fin_level == 'C':
                data.pop("total_price", None)
                data.pop("razorpay_order_id", None)
                
        return data

class OTABlockSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import OTABlock
        model = OTABlock
        fields = ['id', 'room', 'start_date', 'end_date', 'reason', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        if data['end_date'] < data['start_date']:
            raise serializers.ValidationError({"end_date": "End date must be after or equal to start date."})
        return data
