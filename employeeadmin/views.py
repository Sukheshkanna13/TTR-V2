from django.shortcuts import render
from django.utils import timezone
from django.db.models import Q

from rooms.models import Booking, Room
from .decorators import require_employee


@require_employee
def dashboard(request):
    today = timezone.now().date()

    active_bookings = Booking.objects.filter(
        status='CONFIRMED',
        check_in__lte=today,
        check_out__gt=today,
    ).count()

    upcoming_checkouts = Booking.objects.filter(
        status='CONFIRMED',
        check_out=today,
    ).select_related('user', 'room')

    upcoming_checkins = Booking.objects.filter(
        status='CONFIRMED',
        check_in=today,
    ).select_related('user', 'room')

    return render(request, 'employeeadmin/dashboard.html', {
        'active_bookings': active_bookings,
        'upcoming_checkouts': upcoming_checkouts,
        'upcoming_checkins': upcoming_checkins,
        'today': today,
    })


@require_employee
def bookings_list(request):
    bookings = Booking.objects.filter(
        status__in=('CONFIRMED', 'COMPLETED', 'CANCELLED'),
    ).select_related('user', 'room').order_by('-check_in')[:50]
    return render(request, 'employeeadmin/bookings.html', {'bookings': bookings})


@require_employee
def rooms_list(request):
    rooms = Room.objects.all().order_by('city', 'name')
    return render(request, 'employeeadmin/rooms.html', {'rooms': rooms})
