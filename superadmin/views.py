from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum

from rooms.models import Booking, Room
from .decorators import require_super_admin


@require_super_admin
def dashboard(request):
    today = timezone.now().date()
    month_start = today.replace(day=1)

    active_bookings = Booking.objects.filter(
        status='confirmed',
        check_in__lte=today,
        check_out__gt=today,
    ).count()

    today_revenue = Booking.objects.filter(
        status='confirmed',
        check_in=today,
    ).aggregate(total=Sum('total_price'))['total'] or 0

    month_revenue = Booking.objects.filter(
        status='confirmed',
        check_in__gte=month_start,
    ).aggregate(total=Sum('total_price'))['total'] or 0

    total_rooms = Room.objects.count()

    return render(request, 'superadmin/dashboard.html', {
        'active_bookings': active_bookings,
        'today_revenue': today_revenue,
        'month_revenue': month_revenue,
        'total_rooms': total_rooms,
    })


@require_super_admin
def employees_list(request):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    employees = User.objects.filter(userprofile__role='employee').select_related('userprofile')
    return render(request, 'superadmin/employees.html', {'employees': employees})


@require_super_admin
def bookings_list(request):
    bookings = Booking.objects.select_related('user', 'room').order_by('-check_in')[:50]
    return render(request, 'superadmin/bookings.html', {'bookings': bookings})
