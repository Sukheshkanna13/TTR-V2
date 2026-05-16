from django.urls import path
from . import views

app_name = 'employeeadmin'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('bookings/', views.bookings_list, name='bookings'),
    path('rooms/', views.rooms_list, name='rooms'),
    path('rooms/<uuid:room_id>/status/', views.room_status_update, name='room-status-update'),
    path('availability/', views.availability, name='availability'),
    path('availability/block/create/', views.ota_block_create, name='ota-block-create'),
    path('availability/block/<uuid:block_id>/delete/', views.ota_block_delete, name='ota-block-delete'),
    path('availability/rate/create/', views.seasonal_rate_create, name='seasonal-rate-create'),
]
