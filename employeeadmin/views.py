from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from rooms.models import Booking, Room, OTABlock, RoomRate
from .decorators import require_employee


def _fin_level(request):
    """Return the employee's financial access level (A/B/C)."""
    try:
        return request.user.userprofile.fin_level
    except Exception:
        return 'C'


def _assigned_rooms(request):
    """Rooms belonging to properties assigned to this employee."""
    try:
        props = request.user.userprofile.assigned_properties.values_list('id', flat=True)
        if props:
            return Room.objects.filter(property_id__in=props)
    except Exception:
        pass
    return Room.objects.all()


@require_employee
def dashboard(request):
    today = timezone.now().date()
    fin = _fin_level(request)

    active_bookings = Booking.objects.filter(
        status='confirmed',
        check_in__lte=today,
        check_out__gt=today,
    ).count()

    upcoming_checkouts = Booking.objects.filter(
        status='confirmed',
        check_out=today,
    ).select_related('user', 'room')

    upcoming_checkins = Booking.objects.filter(
        status='confirmed',
        check_in=today,
    ).select_related('user', 'room')

    return render(request, 'employeeadmin/dashboard.html', {
        'active_bookings': active_bookings,
        'upcoming_checkouts': upcoming_checkouts,
        'upcoming_checkins': upcoming_checkins,
        'today': today,
        'fin': fin,
    })


@require_employee
def bookings_list(request):
    fin = _fin_level(request)
    bookings = Booking.objects.filter(
        status__in=('confirmed', 'completed', 'cancelled'),
    ).select_related('user', 'room').order_by('-check_in')[:50]
    return render(request, 'employeeadmin/bookings.html', {'bookings': bookings, 'fin': fin})


@require_employee
def rooms_list(request):
    rooms = _assigned_rooms(request).select_related('property').order_by('city', 'name')
    return render(request, 'employeeadmin/rooms.html', {'rooms': rooms, 'fin': _fin_level(request)})


@require_employee
@require_POST
def room_status_update(request, room_id):
    room = get_object_or_404(_assigned_rooms(request), pk=room_id)
    new_status = request.POST.get('operational_status')
    valid = {'available', 'maintenance', 'cleaning', 'out_of_order'}
    if new_status not in valid:
        return JsonResponse({'error': 'Invalid status.'}, status=400)
    room.operational_status = new_status
    room.save(update_fields=['operational_status'])
    return JsonResponse({'message': f'Status updated to {new_status}.', 'status': new_status})


@require_employee
def availability(request):
    fin = _fin_level(request)
    rooms = _assigned_rooms(request).select_related('property').order_by('name')

    selected_room_id = request.GET.get('room')
    selected_room = None
    ota_blocks = []
    seasonal_rates = []

    if selected_room_id:
        selected_room = get_object_or_404(rooms, pk=selected_room_id)
        ota_blocks = OTABlock.objects.filter(room=selected_room).order_by('start_date')
        if fin in ('A', 'B'):
            seasonal_rates = RoomRate.objects.filter(room=selected_room).order_by('start_date')

    return render(request, 'employeeadmin/availability.html', {
        'rooms': rooms,
        'selected_room': selected_room,
        'ota_blocks': ota_blocks,
        'seasonal_rates': seasonal_rates,
        'fin': fin,
    })


@require_employee
@require_POST
def ota_block_create(request):
    room_id = request.POST.get('room_id')
    rooms = _assigned_rooms(request)
    room = get_object_or_404(rooms, pk=room_id)

    start = request.POST.get('start_date')
    end = request.POST.get('end_date')
    reason = request.POST.get('reason', 'Manual Block').strip() or 'Manual Block'

    if not start or not end or start > end:
        return JsonResponse({'error': 'Invalid date range.'}, status=400)

    block = OTABlock.objects.create(room=room, start_date=start, end_date=end, reason=reason)
    return JsonResponse({'message': 'Block created.', 'id': str(block.id)})


@require_employee
@require_POST
def ota_block_delete(request, block_id):
    block = get_object_or_404(OTABlock, pk=block_id)
    if not _assigned_rooms(request).filter(pk=block.room_id).exists():
        return JsonResponse({'error': 'Not authorised.'}, status=403)
    block.delete()
    return JsonResponse({'message': 'Block removed.'})


@require_employee
@require_POST
def seasonal_rate_create(request):
    fin = _fin_level(request)
    if fin == 'C':
        return JsonResponse({'error': 'No financial access.'}, status=403)

    room_id = request.POST.get('room_id')
    room = get_object_or_404(_assigned_rooms(request), pk=room_id)
    start = request.POST.get('start_date')
    end = request.POST.get('end_date')
    price = request.POST.get('price')

    if not all([start, end, price]) or start > end:
        return JsonResponse({'error': 'Invalid data.'}, status=400)

    try:
        price = float(price)
        if price <= 0:
            raise ValueError
    except ValueError:
        return JsonResponse({'error': 'Invalid price.'}, status=400)

    rate = RoomRate.objects.create(room=room, start_date=start, end_date=end, price=price)
    return JsonResponse({'message': 'Rate created.', 'id': str(rate.id)})
