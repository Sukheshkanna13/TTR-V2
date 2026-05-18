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
from django.views.generic import RedirectView
from accounts import views as accounts_views
from rooms import views as rooms_views

urlpatterns = [
    # Core pages
    path("", include("core.urls")),

    # Admin
    path("admin/", admin.site.urls),

    # API endpoints
    path("auth/", include("allauth.urls")),
    path("accounts/", include("accounts.urls")),
    path("rooms/", include("rooms.urls")),
    path("bookings/", include("rooms.booking_urls")),
    path("payments/", include("payments.urls")),
    path("admin-api/employees/create/", accounts_views.CreateEmployeeView.as_view(), name="create_employee"),
    path("admin-portal/login/", RedirectView.as_view(url="/accounts/login/page/", permanent=False), name="admin-portal-login"),
    path("admin-portal/", include("employeeadmin.urls")),
    path("super-admin/login/", RedirectView.as_view(url="/accounts/login/page/", permanent=False), name="super-admin-login"),
    path("super-admin/", include("superadmin.urls")),
    path("api/properties/<uuid:property_id>/calendar/", rooms_views.CalendarView.as_view(), name="property_calendar"),
    path("api/block/", rooms_views.BlockRoomView.as_view(), name="block_room"),
    path("api/unblock/<uuid:pk>/", rooms_views.UnblockRoomView.as_view(), name="unblock_room"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
