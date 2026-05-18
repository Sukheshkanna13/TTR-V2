from django.urls import path
from . import views

app_name = 'employeeadmin'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/live/', views.dashboard_live_data, name='dashboard-live'),
    path('bookings/', views.bookings_list, name='bookings'),
    path('bookings/<uuid:booking_id>/complete/', views.booking_complete, name='booking-complete'),
    # Rooms
    path('rooms/', views.rooms_list, name='rooms'),
    path('rooms/create/', views.room_create, name='room-create'),
    path('rooms/<uuid:room_id>/status/', views.room_status_update, name='room-status-update'),
    path('rooms/<uuid:room_id>/edit/', views.room_edit, name='room-edit'),
    # Room Images
    path('rooms/<uuid:room_id>/images/', views.room_images, name='room-images'),
    path('rooms/<uuid:room_id>/images/upload/', views.room_image_upload, name='room-image-upload'),
    path('rooms/images/<uuid:image_id>/delete/', views.room_image_delete, name='room-image-delete'),
    path('rooms/images/<uuid:image_id>/set-primary/', views.room_image_set_primary, name='room-image-set-primary'),
    # Availability
    path('availability/', views.availability, name='availability'),
    path('availability/block/create/', views.ota_block_create, name='ota-block-create'),
    path('availability/block/<uuid:block_id>/delete/', views.ota_block_delete, name='ota-block-delete'),
    path('availability/rate/create/', views.seasonal_rate_create, name='seasonal-rate-create'),
]
