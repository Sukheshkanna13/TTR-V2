from django.urls import path
from . import views

app_name = 'superadmin'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/live/', views.dashboard_live_data, name='dashboard-live'),
    path('employees/', views.employees_list, name='employees'),
    path('employees/create/', views.employee_create, name='employee-create'),
    path('employees/<int:user_id>/update/', views.employee_update, name='employee-update'),
    path('analytics/', views.analytics, name='analytics'),
    path('tax-config/', views.tax_config, name='tax-config'),
    path('loyalty-config/', views.loyalty_config, name='loyalty-config'),
    path('audit-log/', views.audit_log, name='audit-log'),
    path('bookings/', views.bookings_list, name='bookings'),
    path('bookings/<uuid:booking_id>/cancel/', views.booking_cancel, name='booking-cancel'),
    path('bookings/<uuid:booking_id>/complete/', views.booking_complete, name='booking-complete'),
    # Properties
    path('properties/', views.properties_list, name='properties'),
    path('properties/create/', views.property_create, name='property-create'),
    path('properties/<uuid:property_id>/update/', views.property_update, name='property-update'),
    # Rooms
    path('rooms/', views.rooms_list, name='rooms'),
    path('rooms/create/', views.room_create, name='room-create'),
    path('rooms/<uuid:room_id>/update/', views.room_update, name='room-update'),
    # Room Images
    path('rooms/<uuid:room_id>/images/', views.room_images, name='room-images'),
    path('rooms/<uuid:room_id>/images/upload/', views.room_image_upload, name='room-image-upload'),
    path('rooms/images/<uuid:image_id>/delete/', views.room_image_delete, name='room-image-delete'),
    path('rooms/images/<uuid:image_id>/set-primary/', views.room_image_set_primary, name='room-image-set-primary'),
    # Guests
    path('guests/', views.guests_list, name='guests'),
    path('guests/<int:user_id>/loyalty/', views.loyalty_adjust, name='loyalty-adjust'),
]
