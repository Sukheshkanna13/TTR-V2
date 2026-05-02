"""
Root URL configuration for hotel_booking project.

Structure:
    - Core pages (home, etc.)
    - Admin interface
    - API endpoints (accounts, rooms, bookings, payments)
    - Media files (development only)
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Core pages
    path("", include("core.urls")),

    # Admin
    path("admin/", admin.site.urls),

    # API endpoints
    path("accounts/", include("accounts.urls")),
    path("rooms/", include("rooms.urls")),
    path("bookings/", include("rooms.booking_urls")),
    path("payments/", include("payments.urls")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
