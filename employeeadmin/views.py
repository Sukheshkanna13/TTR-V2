from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from rooms.models import Booking, Room, RoomImage, OTABlock, RoomRate, Property
from .decorators import require_employee


def _fin_level(request):
    """Return the employee's financial access level (A/B/C)."""
    try:
        return request.user.userprofile.fin_level
    except Exception:
        return 'C'


def _assigned_rooms(request):
    """Rooms belonging to properties assigned to this employee.

    Security: an employee with no assigned properties sees NO rooms,
    not all rooms. Prevents privilege escalation when properties are
    not yet assigned on employee creation.
    """
    try:
        props = list(request.user.userprofile.assigned_properties.values_list('id', flat=True))
    except Exception:
        return Room.objects.none()
    if not props:
        return Room.objects.none()
    return Room.objects.filter(property_id__in=props)


@require_employee
def dashboard(request):
    today = timezone.now().date()
    fin = _fin_level(request)
    rooms = _assigned_rooms(request)

    bookings_qs = Booking.objects.filter(room__in=rooms, status='confirmed')

    active_bookings = bookings_qs.filter(check_in__lte=today, check_out__gt=today).count()
    upcoming_checkouts = bookings_qs.filter(check_out=today).select_related('user', 'room')
    upcoming_checkins = bookings_qs.filter(check_in=today).select_related('user', 'room')

    return render(request, 'employeeadmin/dashboard.html', {
        'active_bookings': active_bookings,
        'upcoming_checkouts': upcoming_checkouts,
        'upcoming_checkins': upcoming_checkins,
        'today': today,
        'fin': fin,
    })


@require_employee
def dashboard_live_data(request):
    today = timezone.now().date()
    rooms = _assigned_rooms(request)
    bookings_qs = Booking.objects.filter(room__in=rooms, status='confirmed')
    active_bookings = bookings_qs.filter(check_in__lte=today, check_out__gt=today).count()
    todays_checkins = bookings_qs.filter(check_in=today).count()
    todays_checkouts = bookings_qs.filter(check_out=today).count()
    return JsonResponse({
        'active_bookings': active_bookings,
        'todays_checkins': todays_checkins,
        'todays_checkouts': todays_checkouts,
    })


@require_employee
def bookings_list(request):
    fin = _fin_level(request)
    rooms = _assigned_rooms(request)
    bookings = Booking.objects.filter(
        room__in=rooms,
        status__in=('confirmed', 'completed', 'cancelled'),
    ).select_related('user', 'room', 'room__property').order_by('-check_in')[:50]
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


@require_employee
@require_POST
def booking_complete(request, booking_id):
    """Mark a booking as completed — scoped to employee's assigned properties."""
    rooms = _assigned_rooms(request)
    booking = get_object_or_404(Booking, pk=booking_id, room__in=rooms)
    if booking.status != 'confirmed':
        return JsonResponse({'error': 'Only confirmed bookings can be completed.'}, status=400)
    booking.status = 'completed'
    booking.save(update_fields=['status'])
    return JsonResponse({'message': 'Booking marked as completed.'})


# ── Room CRUD (Scoped) ─────────────────────────────────────────────────────────

def _assigned_properties(request):
    """Properties assigned to this employee."""
    try:
        return request.user.userprofile.assigned_properties.all()
    except Exception:
        return Property.objects.none()


@require_employee
@require_POST
def room_create(request):
    """Create a room — only within assigned properties."""
    property_id = request.POST.get('property_id')
    props = _assigned_properties(request)
    prop = get_object_or_404(Property, pk=property_id)
    if prop not in props:
        return JsonResponse({'error': 'Not assigned to this property.'}, status=403)

    name = request.POST.get('name', '').strip()
    room_type = request.POST.get('room_type', 'single')
    price = request.POST.get('price_per_night', '0')
    capacity = request.POST.get('capacity', '2')
    amenities = request.POST.get('amenities', '').strip()
    description = request.POST.get('description', '').strip()

    if not name:
        return JsonResponse({'error': 'Room name is required.'}, status=400)
    try:
        price = Decimal(price)
        capacity = int(capacity)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid price or capacity.'}, status=400)

    room = Room.objects.create(
        property=prop, name=name, city=prop.city, room_type=room_type,
        price_per_night=price, capacity=capacity, amenities=amenities,
        description=description,
    )
    return JsonResponse({'message': f'Room "{room.name}" created.', 'id': str(room.id)})


@require_employee
@require_POST
def room_edit(request, room_id):
    """Edit room details — scoped to assigned properties."""
    import json
    rooms = _assigned_rooms(request)
    room = get_object_or_404(Room, pk=room_id)
    if room not in rooms:
        return JsonResponse({'error': 'Not assigned to this room\'s property.'}, status=403)

    data = json.loads(request.body)
    action = data.get('action')

    if action == 'update_details':
        for field in ('name', 'price_per_night', 'capacity', 'amenities', 'description'):
            val = data.get(field)
            if val is not None:
                if field == 'price_per_night':
                    val = Decimal(str(val))
                elif field == 'capacity':
                    val = int(val)
                setattr(room, field, val)
        room.save()
        return JsonResponse({'message': 'Room updated.'})

    if action == 'set_status':
        new_status = data.get('operational_status', '')
        valid = {s for s, _ in Room.OPERATIONAL_STATUS_CHOICES}
        if new_status not in valid:
            return JsonResponse({'error': 'Invalid status.'}, status=400)
        room.operational_status = new_status
        room.save(update_fields=['operational_status'])
        return JsonResponse({'message': f'Status set to {new_status}.'})

    if action == 'toggle_active':
        room.is_active = not room.is_active
        room.save(update_fields=['is_active'])
        return JsonResponse({'message': f'Room {"activated" if room.is_active else "deactivated"}.', 'is_active': room.is_active})

    return JsonResponse({'error': 'Unknown action.'}, status=400)


# ── Room Image Management (Scoped) ─────────────────────────────────────────────

@require_employee
def room_images(request, room_id):
    rooms = _assigned_rooms(request)
    room = get_object_or_404(Room, pk=room_id)
    if room not in rooms:
        return JsonResponse({'error': 'Not assigned.'}, status=403)
    images = room.images.all().order_by('order', '-is_primary')
    return render(request, 'employeeadmin/room_images.html', {
        'room': room,
        'images': images,
    })


@require_employee
@require_POST
def room_image_upload(request, room_id):
    rooms = _assigned_rooms(request)
    room = get_object_or_404(Room, pk=room_id)
    if room not in rooms:
        return JsonResponse({'error': 'Not assigned.'}, status=403)

    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'No image file.'}, status=400)

    caption = request.POST.get('caption', '').strip()
    is_primary = request.POST.get('is_primary') == 'on'
    if is_primary:
        room.images.filter(is_primary=True).update(is_primary=False)

    RoomImage.objects.create(
        room=room, image=image_file, caption=caption, is_primary=is_primary,
        order=room.images.count(),
    )
    return JsonResponse({'message': 'Image uploaded.'})


@require_employee
@require_POST
def room_image_delete(request, image_id):
    rooms = _assigned_rooms(request)
    img = get_object_or_404(RoomImage, pk=image_id)
    if img.room not in rooms:
        return JsonResponse({'error': 'Not assigned.'}, status=403)
    img.image.delete(save=False)
    img.delete()
    return JsonResponse({'message': 'Image deleted.'})


@require_employee
@require_POST
def room_image_set_primary(request, image_id):
    rooms = _assigned_rooms(request)
    img = get_object_or_404(RoomImage, pk=image_id)
    if img.room not in rooms:
        return JsonResponse({'error': 'Not assigned.'}, status=403)
    img.room.images.filter(is_primary=True).update(is_primary=False)
    img.is_primary = True
    img.save(update_fields=['is_primary'])
    return JsonResponse({'message': 'Set as primary.'})

