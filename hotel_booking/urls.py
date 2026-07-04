"""
Root URL configuration for hotel_booking project.

Structure:
    - Core pages (home, etc.)
    - Admin interface
    - API endpoints (accounts, rooms, bookings, payments)
    - Admin portals (employee, super-admin)
    - Media files (development only)
"""

# pyrefly: ignore [missing-import]
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

# Customise the standard Django admin site header/title
admin.site.site_header = "Temples & Towns"
admin.site.site_title = "T&T Admin"
admin.site.index_title = "Management Dashboard"

urlpatterns = [
    # Core pages
    path("", include("core.urls")),

    # Django admin
    path("admin/", admin.site.urls),

    # Auth & API endpoints
    path("auth/", include("allauth.urls")),
    path("accounts/", include("accounts.urls")),
    path("rooms/", include("rooms.urls")),
    path("bookings/", include("rooms.booking_urls")),
    path("payments/", include("payments.urls")),

    # Admin portals
    path("admin-portal/login/", RedirectView.as_view(url="/accounts/login/page/", permanent=False), name="admin-portal-login"),
    path("admin-portal/", include("employeeadmin.urls")),
    path("super-admin/login/", RedirectView.as_view(url="/accounts/login/page/", permanent=False), name="super-admin-login"),
    path("super-admin/", include("superadmin.urls")),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
