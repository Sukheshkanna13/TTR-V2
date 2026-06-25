"""
URL configuration for booking endpoints.

Routes:
    Page Views:
        /bookings/my-bookings/page/         — My bookings page
        /bookings/confirmation/page/        — Booking confirmation page
    
    API Endpoints:
        POST /bookings/hold/                — Hold a room
        POST /bookings/<id>/pay/            — Process payment
        POST /bookings/<id>/cancel/         — Cancel booking
        GET  /bookings/<id>/                — Get booking details
        GET  /bookings/ref/<ref>/confirmation/ — Get confirmation data
        GET  /bookings/my/                  — List user's bookings
"""

from django.urls import path

from rooms import views

app_name = "bookings"

urlpatterns = [
    # Page views

    path("confirmation/page/", views.confirmation_page, name="confirmation-page"),

    # API endpoints
    path("hold/", views.HoldRoomView.as_view(), name="hold"),
    path("<uuid:booking_id>/pay/", views.ProcessPaymentView.as_view(), name="pay"),
    path("<uuid:booking_id>/cancel/", views.CancelBookingView.as_view(), name="cancel"),
    path("<uuid:booking_id>/release/", views.ReleaseHoldView.as_view(), name="release"),
    path("<uuid:booking_id>/", views.BookingDetailView.as_view(), name="detail"),
    path("ref/<str:booking_ref>/confirmation/", views.ConfirmationView.as_view(), name="confirmation"),
    path("my/", views.MyBookingsView.as_view(), name="my-bookings"),
]
