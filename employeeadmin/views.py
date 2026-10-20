import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from rooms.models import Booking, Room, RoomImage, OTABlock, RoomRate, Property
from .decorators import require_employee
from core.admin_utils import (
    BadInput, audit, clean_uuid, parse_json, to_date, to_decimal, to_int,
)
from core.constants import UNKNOWN_ACTION_ERR

logger = logging.getLogger(__name__)
NOT_ASSIGNED_MSG = 'Not assigned.'
NO_FIN_MSG = 'No financial access.'
ARI_HORIZON_DAYS = 500
MAX_PRICE = '99999999.99'   # Room.price_per_night / RoomRate.price: max_digits=10, decimal_places=2
MAX_ROOM_CAPACITY = 20


def _fin_level(request):
    """Return the employee's financial access level (A/B/C)."""
    try:
        return request.user.userprofile.fin_level
    except Exception:
        return 'C'


def _has_fin_access(request):
    """Fin levels A and B may see/change money; C may not.

    Mirrors the existing ``fin == 'C'`` checks: a legacy profile with a blank
    level is not blocked here (superadmin always assigns A/B/C on creation).
    """
    return _fin_level(request) != 'C'


def _no_fin_response():
    return JsonResponse({'error': NO_FIN_MSG}, status=403)


def _push_ari(room, change_types, start=None, end=None):
    """Tell Channex that ARI changed. Defaults to today -> today + 500 days (end exclusive)."""
    from core.ota.dispatch import record_ari_change
    today = date.today()
    record_ari_change(
        room.room_type, room.property_id,
        start or today, end or today + timedelta(days=ARI_HORIZON_DAYS),
        change_types=change_types,
    )


def _clean_room_type(value):
    if value not in {k for k, _ in Room.ROOM_TYPE_CHOICES}:
        raise BadInput('Invalid room type.')
    return value


def _clean_price(value, field='price'):
    price = to_decimal(value, field, max_value=MAX_PRICE).quantize(Decimal('0.01'), ROUND_HALF_UP)
    if price <= 0:
        raise BadInput(f'{field} must be greater than zero.')
    return price


def _clean_capacity(value):
    return to_int(value, 'capacity', min_value=1, max_value=MAX_ROOM_CAPACITY)


def _clean_rating(value):
    return to_decimal(value, 'rating', min_value=0, max_value=5).quantize(Decimal('0.1'), ROUND_HALF_UP)


def _clean_name(value):
    name = str(value).strip()
    if not name:
        raise BadInput('Room name is required.')
    if len(name) > 100:
        raise BadInput('Room name must be at most 100 characters.')
    return name


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
    from payments.models import Payment
    fin = _fin_level(request)
    rooms = _assigned_rooms(request)
    bookings_qs = Booking.objects.filter(
        room__in=rooms,
        status__in=('confirmed', 'completed', 'cancelled'),
    ).select_related('user', 'room', 'room__property').order_by('-check_in')
    
    paginator = Paginator(bookings_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    available_rooms = rooms.filter(is_active=True).select_related('property').order_by('property__name', 'name')
    
    return render(request, 'employeeadmin/bookings.html', {
        'bookings': page_obj, 
        'page_obj': page_obj,
        'fin': fin,
        'assigned_rooms': available_rooms,
        'payment_methods': Payment.METHOD_CHOICES,
    })


@require_employee
@require_POST
def walk_in_booking_create(request):
    from rooms.services import create_walk_in_booking
    from payments.models import Payment

    try:
        room_id = clean_uuid(request.POST.get('room_id'))
        if room_id is None:
            raise BadInput('Invalid room.')
        room = get_object_or_404(_assigned_rooms(request), pk=room_id)

        override_val = request.POST.get('price_override', '').strip()
        if override_val and not _has_fin_access(request):
            return _no_fin_response()

        check_in = to_date(request.POST.get('check_in', ''), 'check-in')
        check_out = to_date(request.POST.get('check_out', ''), 'check-out')

        guest_name = request.POST.get('guest_name', '').strip()
        guest_phone = request.POST.get('guest_phone', '').strip()
        if not guest_name or not guest_phone:
            raise BadInput('Guest name and phone number are required.')

        guests = to_int(request.POST.get('guests', '1'), 'guests', min_value=1)
        if guests > room.capacity:
            raise BadInput(f'Guests must be between 1 and {room.capacity} for this room.')

        price_override = None
        if override_val:
            price_override = _clean_price(override_val, 'Price override')
    except BadInput as e:
        return e.response()

    payment_method = request.POST.get('payment_method', Payment.METHOD_CASH)
    try:
        booking = create_walk_in_booking(
            room=room,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            guest_name=guest_name,
            guest_phone=guest_phone,
            guest_email=request.POST.get('guest_email', '').strip(),
            guest_id_type=request.POST.get('guest_id_type', '').strip(),
            guest_id_number=request.POST.get('guest_id_number', '').strip(),
            payment_method=payment_method,
            price_override=price_override,
            created_by_staff=request.user,
            operational_notes=request.POST.get('operational_notes', '').strip(),
        )
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.exception("Error creating walk-in booking: %s", e)
        return JsonResponse({'error': 'Internal server error while creating booking.'}, status=500)

    audit(request, 'WALK_IN_BOOKING_CREATED', detail=(
        f"ref={booking.booking_reference}, room={room.name}, {check_in}->{check_out}, "
        f"guests={guests}, method={payment_method}, price={booking.total_price}"
        f"{' (override)' if price_override is not None else ''}"
    ))
    return JsonResponse({
        'message': f'Walk-in booking created successfully. Ref: {booking.booking_reference}',
        'booking_reference': booking.booking_reference,
        'booking_id': str(booking.id),
    })


@require_employee
def rooms_list(request):
    property_filter = clean_uuid(request.GET.get('property')) or ''
    rooms_qs = _assigned_rooms(request).select_related('property').order_by('property__name', 'name')
    if property_filter:
        rooms_qs = rooms_qs.filter(property_id=property_filter)
        
    paginator = Paginator(rooms_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    properties = _assigned_properties(request).filter(is_active=True).order_by('name')
    return render(request, 'employeeadmin/rooms.html', {
        'rooms': page_obj,
        'page_obj': page_obj,
        'properties': properties,
        'property_filter': property_filter,
        'operational_choices': Room.OPERATIONAL_STATUS_CHOICES,
        'fin': _fin_level(request),
    })


def _apply_room_status(request, room, new_status):
    """Validate + save an operational status, push availability, audit. Returns an error response or None."""
    if new_status not in {k for k, _ in Room.OPERATIONAL_STATUS_CHOICES}:
        return JsonResponse({'error': 'Invalid status.'}, status=400)
    old_status = room.operational_status
    room.operational_status = new_status
    room.save(update_fields=['operational_status'])
    # C7.2: status change affects availability for all future dates
    _push_ari(room, ("availability",))
    audit(request, 'ROOM_STATUS_UPDATED', detail=f"Room {room.name}: {old_status}->{new_status}")
    return None


@require_employee
@require_POST
def room_status_update(request, room_id):
    room = get_object_or_404(_assigned_rooms(request), pk=room_id)
    new_status = request.POST.get('operational_status')
    error = _apply_room_status(request, room, new_status)
    if error:
        return error
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
        # An unparseable id resolves to pk=None, which 404s like any unknown room.
        selected_room = get_object_or_404(rooms, pk=clean_uuid(selected_room_id))
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
    """Block a room for [start, end). ``end`` is exclusive, like every availability query."""
    try:
        room_id = clean_uuid(request.POST.get('room_id'))
        if room_id is None:
            raise BadInput('Invalid room.')
        room = get_object_or_404(_assigned_rooms(request), pk=room_id)

        start = to_date(request.POST.get('start_date', ''), 'start date')
        end = to_date(request.POST.get('end_date', ''), 'end date')
        reason = request.POST.get('reason', 'Manual Block').strip() or 'Manual Block'
        if len(reason) > 255:
            raise BadInput('Reason must be at most 255 characters.')
        if start >= end:
            raise BadInput('End date must be after the start date.')

        with transaction.atomic():
            # Same lock the booking flows take, so a booking can't slip in between check and create.
            Room.objects.select_for_update().get(pk=room.pk)
            clashes = list(
                Booking.objects.filter(
                    room=room, status='confirmed', check_in__lt=end, check_out__gt=start,
                ).order_by('check_in').values_list('booking_reference', 'check_in', 'check_out')[:5]
            )
            if clashes:
                refs = ', '.join(f'{ref} ({ci} to {co})' for ref, ci, co in clashes)
                raise BadInput(f'Block overlaps confirmed booking(s): {refs}.')
            block = OTABlock.objects.create(room=room, start_date=start, end_date=end, reason=reason)
    except BadInput as e:
        return e.response()

    # C7.2: blocking a room reduces availability for those dates -> notify Channex
    _push_ari(room, ("availability",), start, end)
    audit(request, 'OTA_BLOCK_CREATED', detail=f"Room {room.name}: {start} to {end} ({reason})")
    return JsonResponse({'message': 'Block created.', 'id': str(block.id)})


@require_employee
@require_POST
def ota_block_delete(request, block_id):
    block = get_object_or_404(OTABlock, pk=block_id)
    if not _assigned_rooms(request).filter(pk=block.room_id).exists():
        return JsonResponse({'error': 'Not authorised.'}, status=403)
    # C7.2: capture dates + room info before delete (inaccessible after)
    room = block.room
    start, end = block.start_date, block.end_date
    block.delete()
    # Removing a block frees availability for those dates -> notify Channex
    _push_ari(room, ("availability",), start, end)
    audit(request, 'OTA_BLOCK_DELETED', detail=f"Room {room.name}: {start} to {end}")
    return JsonResponse({'message': 'Block removed.'})


@require_employee
@require_POST
def seasonal_rate_create(request):
    if not _has_fin_access(request):
        return _no_fin_response()

    try:
        room_id = clean_uuid(request.POST.get('room_id'))
        if room_id is None:
            raise BadInput('Invalid room.')
        room = get_object_or_404(_assigned_rooms(request), pk=room_id)

        start = to_date(request.POST.get('start_date', ''), 'start date')
        end = to_date(request.POST.get('end_date', ''), 'end date')
        price = _clean_price(request.POST.get('price', ''), 'Price')
        if start >= end:
            raise BadInput('End date must be after the start date.')
    except BadInput as e:
        return e.response()

    rate = RoomRate.objects.create(room=room, start_date=start, end_date=end, price=price)
    # C7.2: new rate/restriction row -> push rates+restrictions for that date range
    _push_ari(room, ("rates", "restrictions"), start, end)
    audit(request, 'ROOM_RATE_CREATED', detail=f"Room {room.name}: {price} per night, {start} to {end}")
    return JsonResponse({'message': 'Rate created.', 'id': str(rate.id)})


@require_employee
@require_POST
def booking_complete(request, booking_id):
    """Mark a booking as completed — scoped to employee's assigned properties."""
    rooms = _assigned_rooms(request)
    booking = get_object_or_404(Booking.objects.select_related('room'), pk=booking_id, room__in=rooms)
    original_check_out = booking.check_out
    try:
        booking.complete_stay()
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    detail = f"ref={booking.booking_reference}, room={booking.room.name}"
    if booking.check_out != original_check_out:
        detail += f", early checkout {original_check_out}->{booking.check_out}"
    audit(request, 'BOOKING_COMPLETED', detail=detail)
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
    """Create a room — only within assigned properties.

    A price is mandatory for a room, and fin level C may not set prices,
    so level C cannot create rooms at all.
    """
    if not _has_fin_access(request):
        return _no_fin_response()

    try:
        property_id = clean_uuid(request.POST.get('property_id'))
        if property_id is None:
            raise BadInput('Invalid property.')
        prop = get_object_or_404(Property, pk=property_id)
        if not _assigned_properties(request).filter(pk=prop.pk).exists():
            return JsonResponse({'error': 'Not assigned to this property.'}, status=403)

        name = _clean_name(request.POST.get('name', ''))
        room_type = _clean_room_type(request.POST.get('room_type', 'single'))
        price = _clean_price(request.POST.get('price_per_night', ''), 'Price')
        capacity = _clean_capacity(request.POST.get('capacity', '2'))
        rating_str = request.POST.get('rating', '').strip()
        rating_val = _clean_rating(rating_str) if rating_str else Decimal("4.5")
    except BadInput as e:
        return e.response()

    room = Room.objects.create(
        property=prop, name=name, city=prop.city, room_type=room_type,
        price_per_night=price, capacity=capacity,
        amenities=request.POST.get('amenities', '').strip(),
        description=request.POST.get('description', '').strip(),
        rating=rating_val,
    )
    _push_ari(room, ("availability",))
    audit(request, 'ROOM_CREATED', detail=(
        f"Room {room.name} at {prop.name}: type={room_type}, price={price}, capacity={capacity}"
    ))
    return JsonResponse({'message': f'Room "{room.name}" created.', 'id': str(room.id)})


def _handle_room_update_details(request, room, data):
    # Money first: level C may not touch price at all (other fields still work).
    price_in_payload = data.get('price_per_night') is not None
    if price_in_payload and not _has_fin_access(request):
        return _no_fin_response()

    # Validate everything before mutating anything.
    changes = {}
    if data.get('name') is not None:
        changes['name'] = _clean_name(data['name'])
    if data.get('room_type') is not None:
        # Validated but deliberately not applied: changing a room's type would also
        # need old/new type availability pushes to Channex (pre-existing behaviour).
        _clean_room_type(data['room_type'])
    if price_in_payload:
        changes['price_per_night'] = _clean_price(data['price_per_night'], 'Price')
    if data.get('capacity') is not None:
        changes['capacity'] = _clean_capacity(data['capacity'])
    if data.get('amenities') is not None:
        changes['amenities'] = str(data['amenities'])
    if data.get('description') is not None:
        changes['description'] = str(data['description'])
    # Rating: explicit null/blank clears to the default, a value sets
    if 'rating' in data:
        r = data['rating']
        changes['rating'] = _clean_rating(r) if r is not None and str(r).strip() else Decimal("4.5")

    old_price = room.price_per_night
    for field, value in changes.items():
        setattr(room, field, value)
    if changes:
        room.save(update_fields=list(changes))

    price_changed = 'price_per_night' in changes and changes['price_per_night'] != old_price
    # C7.2: price change -> push updated rates for all future dates
    if price_changed:
        _push_ari(room, ("rates",))

    detail = f"Room {room.name}: updated {', '.join(changes) or 'nothing'}"
    if price_changed:
        detail += f"; price {old_price}->{changes['price_per_night']}"
    audit(request, 'ROOM_UPDATED', detail=detail)
    return JsonResponse({'message': 'Room updated.'})


def _handle_room_set_status(request, room, data):
    new_status = data.get('operational_status', '')
    error = _apply_room_status(request, room, new_status)
    if error:
        return error
    return JsonResponse({'message': f'Status set to {new_status}.'})


@require_employee
@require_POST
def room_edit(request, room_id):
    """Edit room details — scoped to assigned properties."""
    rooms = _assigned_rooms(request)
    room = get_object_or_404(Room, pk=room_id)
    if room not in rooms:
        return JsonResponse({'error': 'Not assigned to this room\'s property.'}, status=403)

    try:
        data = parse_json(request)
        action = data.get('action')

        if action == 'update_details':
            return _handle_room_update_details(request, room, data)

        if action == 'set_status':
            return _handle_room_set_status(request, room, data)
    except BadInput as e:
        return e.response()

    if action == 'toggle_active':
        room.is_active = not room.is_active
        room.save(update_fields=['is_active'])
        # An inactive room is not sellable, so availability changes for all future dates
        _push_ari(room, ("availability",))
        state = "activated" if room.is_active else "deactivated"
        audit(request, 'ROOM_UPDATED', detail=f"Room {room.name} {state}")
        return JsonResponse({'message': f'Room {state}.', 'is_active': room.is_active})

    if action == 'toggle_featured':
        room.is_featured = not room.is_featured
        room.save(update_fields=['is_featured'])
        state = "featured" if room.is_featured else "unfeatured"
        audit(request, 'ROOM_UPDATED', detail=f"Room {room.name} {state}")
        return JsonResponse({'message': f'Room {state}.', 'is_featured': room.is_featured})

    return JsonResponse({'error': UNKNOWN_ACTION_ERR}, status=400)


# ── Room Image Management (Scoped) ─────────────────────────────────────────────

@require_employee
def room_images(request, room_id):
    room = get_object_or_404(_assigned_rooms(request), pk=room_id)
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
        return JsonResponse({'error': NOT_ASSIGNED_MSG}, status=403)

    image_files = request.FILES.getlist('image')
    if not image_files:
        return JsonResponse({'error': 'No image files provided.'}, status=400)

    caption = request.POST.get('caption', '').strip()
    is_primary = request.POST.get('is_primary') == 'on'
    
    if is_primary:
        room.images.filter(is_primary=True).update(is_primary=False)

    for idx, image_file in enumerate(image_files):
        primary = is_primary if idx == 0 else False
        RoomImage.objects.create(
            room=room, image=image_file, caption=caption, is_primary=primary,
            order=room.images.count(),
        )

    audit(request, 'ROOM_IMAGE_UPLOADED', detail=f"Room {room.name}: {len(image_files)} image(s)")
    return JsonResponse({'message': f'{len(image_files)} image(s) uploaded.'})


@require_employee
@require_POST
def room_image_delete(request, image_id):
    rooms = _assigned_rooms(request)
    img = get_object_or_404(RoomImage, pk=image_id)
    if img.room not in rooms:
        return JsonResponse({'error': NOT_ASSIGNED_MSG}, status=403)
    room_name = img.room.name
    img.image.delete(save=False)
    img.delete()
    audit(request, 'ROOM_IMAGE_DELETED', detail=f"Room {room_name}: image {image_id}")
    return JsonResponse({'message': 'Image deleted.'})


@require_employee
@require_POST
def room_image_set_primary(request, image_id):
    rooms = _assigned_rooms(request)
    img = get_object_or_404(RoomImage, pk=image_id)
    if img.room not in rooms:
        return JsonResponse({'error': NOT_ASSIGNED_MSG}, status=403)
    img.room.images.filter(is_primary=True).update(is_primary=False)
    img.is_primary = True
    img.save(update_fields=['is_primary'])
    audit(request, 'ROOM_IMAGE_PRIMARY_SET', detail=f"Room {img.room.name}: image {image_id}")
    return JsonResponse({'message': 'Set as primary.'})



# ── Room Status Board (scoped) ─────────────────────────────────────────────────

@require_employee
def room_status_board(request):
    rooms = _assigned_rooms(request).select_related('property').order_by('property__name', 'name')
    return render(request, 'employeeadmin/room_status_board.html', {
        'rooms': rooms,
        'status_choices': Room.OPERATIONAL_STATUS_CHOICES,
    })


@require_employee
def room_status_board_data(request):
    rooms = _assigned_rooms(request).select_related('property').order_by('property__name', 'name')
    return JsonResponse({
        'rooms': [
            {
                'id': str(r.id),
                'name': r.name,
                'property': r.property.name,
                'status': r.operational_status,
                'is_active': r.is_active,
            }
            for r in rooms
        ]
    })
