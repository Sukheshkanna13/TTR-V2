from django.urls import path
from . import views

app_name = 'superadmin'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
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
]
