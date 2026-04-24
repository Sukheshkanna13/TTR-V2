"""
Root URL configuration for hotel_booking project.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("rooms/", include("rooms.urls")),
    path("bookings/", include("rooms.booking_urls")),
    path("payments/", include("payments.urls")),
]
