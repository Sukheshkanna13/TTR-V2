from django.urls import path
from . import views

app_name = 'superadmin'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('employees/', views.employees_list, name='employees'),
    path('bookings/', views.bookings_list, name='bookings'),
]
