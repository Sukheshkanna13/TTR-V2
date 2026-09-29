"""
DRF session-authenticated endpoints must enforce CSRF. They previously used
CsrfExemptSessionAuthentication globally, so any cross-site request carrying the
guest's session cookie could hold/cancel/pay.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import UserProfile
from rooms.models import Booking, Property, Room

User = get_user_model()


class ApiCsrfEnforcementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="csrf.guest@example.com", phone="+919876500000",
            password="strongpassword123", full_name="Csrf Guest", is_active=True,
        )
        UserProfile.objects.get_or_create(user=self.user)
        prop = Property.objects.create(name="Pondy", city="Pondicherry", address="12 White Town")
        room = Room.objects.create(
            property=prop, name="Deluxe", room_type="deluxe",
            price_per_night=Decimal("2000.00"), capacity=2,
        )
        self.booking = Booking.objects.create(
            user=self.user, room=room,
            check_in=date.today() + timedelta(days=5),
            check_out=date.today() + timedelta(days=7),
            guests=2, total_price=Decimal("4000.00"), status="pending",
            hold_expires_at=timezone.now() + timedelta(minutes=10),
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.url = f"/bookings/{self.booking.id}/cancel/"

    def _csrf_token(self):
        self.client.get("/accounts/login/page/")  # any page that sets the cookie
        return self.client.cookies["csrftoken"].value

    def test_authenticated_post_without_token_is_rejected(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "pending")

    def test_authenticated_post_with_token_succeeds(self):
        token = self._csrf_token()
        response = self.client.post(self.url, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, "cancelled")

    def test_anonymous_login_post_needs_no_token(self):
        anon = Client(enforce_csrf_checks=True)
        response = anon.post(
            "/accounts/login/",
            {"email": "csrf.guest@example.com", "password": "strongpassword123"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def test_razorpay_webhook_is_not_csrf_checked(self):
        anon = Client(enforce_csrf_checks=True)
        response = anon.post("/payments/webhook/", "{}", content_type="application/json")
        # Reaches the view (missing signature -> 400), not blocked by CSRF (403)
        self.assertEqual(response.status_code, 400)
