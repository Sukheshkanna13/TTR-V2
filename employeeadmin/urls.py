from django.urls import path
from . import views

app_name = 'employeeadmin'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('bookings/', views.bookings_list, name='bookings'),
    path('rooms/', views.rooms_list, name='rooms'),
]
