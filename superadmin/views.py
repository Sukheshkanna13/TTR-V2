import json
import secrets
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from rooms.models import Booking, Room, RoomImage, Property
from .decorators import require_super_admin
from .models import AuditLog, PropertyTaxConfig

User = get_user_model()


def _log(request, action, target_user=None, detail=''):
    AuditLog.objects.create(
        actor=request.user,
        action=action,
        target_user=target_user,
        detail=detail,
        ip_address=request.META.get('REMOTE_ADDR'),
    )


# ── Dashboard ──────────────────────────────────────────────────────────────────

@require_super_admin
def dashboard(request):
    today = timezone.now().date()
    month_start = today.replace(day=1)

    active_bookings = Booking.objects.filter(
        status='confirmed', check_in__lte=today, check_out__gt=today,
    ).count()

    todays_arrivals = list(Booking.objects.filter(
        status='confirmed', check_in=today,
    ).select_related('user', 'room__property'))

    todays_departures = list(Booking.objects.filter(
        status='confirmed', check_out=today,
    ).select_related('user', 'room__property'))

    pending_holds = list(Booking.objects.filter(
        status='pending',
    ).select_related('user', 'room__property').order_by('created_at')[:20])

    today_revenue = sum(b.total_price for b in todays_arrivals)

    month_revenue = Booking.objects.filter(
        status='confirmed', check_in__gte=month_start,
    ).aggregate(t=Sum('total_price'))['t'] or 0

    total_rooms = Room.objects.count()
    total_guests = User.objects.filter(userprofile__role='guest').count()

    recent_bookings = Booking.objects.select_related(
        'user', 'room__property'
    ).order_by('-created_at')[:8]

    return render(request, 'superadmin/dashboard.html', {
        'active_bookings': active_bookings,
        'todays_arrivals': todays_arrivals,
        'todays_departures': todays_departures,
        'pending_holds': pending_holds,
        'todays_checkins': len(todays_arrivals),
        'todays_checkouts': len(todays_departures),
        'today_revenue': today_revenue,
        'month_revenue': month_revenue,
        'total_rooms': total_rooms,
        'total_guests': total_guests,
        'recent_bookings': recent_bookings,
    })


@require_super_admin
def dashboard_live_data(request):
    today = timezone.now().date()

    active_bookings = Booking.objects.filter(
        status='confirmed', check_in__lte=today, check_out__gte=today,
    ).count()

    todays_checkins = Booking.objects.filter(
        status='confirmed', check_in=today,
    ).count()

    todays_checkouts = Booking.objects.filter(
        status='confirmed', check_out=today,
    ).count()

    today_revenue = Booking.objects.filter(
        status='confirmed', check_in__gte=today,
    ).aggregate(t=Sum('total_price'))['t'] or 0

    pending_qs = Booking.objects.filter(
        status='pending',
    ).select_related('user', 'room__property').order_by('created_at')[:20]

    pending_holds = []
    for b in pending_qs:
        reference = b.booking_reference if b.booking_reference else str(b.id)[:8]
        guest = b.user.full_name if b.user.full_name else b.user.email
        room_name = b.room.name if b.room else ''
        property_name = b.room.property.name if b.room and b.room.property else ''
        pending_holds.append({
            'id': str(b.id),
            'reference': reference,
            'guest': guest,
            'room': room_name,
            'property': property_name,
            'check_in': str(b.check_in),
            'expires_at': b.hold_expires_at.isoformat() if b.hold_expires_at else None,
        })

    return JsonResponse({
        'active_bookings': active_bookings,
        'todays_checkins': todays_checkins,
        'todays_checkouts': todays_checkouts,
        'today_revenue': float(today_revenue),
        'pending_holds': pending_holds,
    })


# ── Employee CRUD ──────────────────────────────────────────────────────────────

@require_super_admin
def employees_list(request):
    employees = User.objects.filter(
        userprofile__role='employee'
    ).select_related('userprofile').prefetch_related('userprofile__assigned_properties')
    properties = Property.objects.filter(is_active=True)
    return render(request, 'superadmin/employees.html', {
        'employees': employees,
        'properties': properties,
    })


@require_super_admin
@require_POST
def employee_create(request):
    email = request.POST.get('email', '').strip().lower()
    full_name = request.POST.get('full_name', '').strip()
    fin_level = request.POST.get('fin_level', 'C')
    property_ids = request.POST.getlist('properties')

    errors = []
    if not email or '@' not in email:
        errors.append('Valid email required.')
    if User.objects.filter(email=email).exists():
        errors.append('Email already in use.')
    if not full_name:
        errors.append('Full name required.')

    if errors:
        return JsonResponse({'error': ' '.join(errors)}, status=400)

    temp_password = secrets.token_urlsafe(12)
    user = User.objects.create(
        email=email,
        full_name=full_name,
        password=make_password(temp_password),
        is_active=True,
    )
    from accounts.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = 'employee'
    profile.fin_level = fin_level
    profile.must_change_password = True
    profile.save()
    if property_ids:
        profile.assigned_properties.set(Property.objects.filter(id__in=property_ids))

    _log(request, 'EMPLOYEE_CREATED', target_user=user,
         detail=f"fin_level={fin_level}, properties={property_ids}")

    return JsonResponse({
        'message': f'Employee created. Temp password: {temp_password}',
        'temp_password': temp_password,
    })


@require_super_admin
@require_POST
def employee_update(request, user_id):
    employee = get_object_or_404(User, pk=user_id)
    data = json.loads(request.body)
    action = data.get('action')

    if action == 'lock':
        employee.is_active = False
        employee.save(update_fields=['is_active'])
        _log(request, 'EMPLOYEE_LOCKED', target_user=employee)
        return JsonResponse({'message': 'Account locked.'})

    if action == 'unlock':
        employee.is_active = True
        employee.save(update_fields=['is_active'])
        _log(request, 'EMPLOYEE_UNLOCKED', target_user=employee)
        return JsonResponse({'message': 'Account unlocked.'})

    if action == 'reset_password':
        temp = secrets.token_urlsafe(12)
        employee.set_password(temp)
        employee.save()
        employee.userprofile.must_change_password = True
        employee.userprofile.save(update_fields=['must_change_password'])
        _log(request, 'PASSWORD_RESET', target_user=employee)
        return JsonResponse({'message': f'Password reset. New temp: {temp}', 'temp_password': temp})

    if action == 'update_fin':
        fin = data.get('fin_level', 'C')
        employee.userprofile.fin_level = fin
        employee.userprofile.save(update_fields=['fin_level'])
        _log(request, 'EMPLOYEE_UPDATED', target_user=employee, detail=f"fin_level→{fin}")
        return JsonResponse({'message': 'Financial level updated.'})

    if action == 'update_properties':
        prop_ids = data.get('property_ids', [])
        employee.userprofile.assigned_properties.set(
            Property.objects.filter(id__in=prop_ids)
        )
        _log(request, 'EMPLOYEE_UPDATED', target_user=employee,
             detail=f"properties={prop_ids}")
        return JsonResponse({'message': 'Properties updated.'})

    return JsonResponse({'error': 'Unknown action.'}, status=400)


# ── Analytics ──────────────────────────────────────────────────────────────────

@require_super_admin
def analytics(request):
    import datetime as dt
    today = timezone.now().date()

    date_from_str = request.GET.get('from', '')
    date_to_str = request.GET.get('to', '')
    try:
        date_from = dt.date.fromisoformat(date_from_str) if date_from_str else today.replace(day=1)
    except ValueError:
        date_from = today.replace(day=1)
    try:
        date_to = dt.date.fromisoformat(date_to_str) if date_to_str else today
    except ValueError:
        date_to = today

    confirmed_qs = Booking.objects.filter(
        status='confirmed', check_in__gte=date_from, check_in__lte=date_to,
    )

    agg = confirmed_qs.aggregate(
        total_revenue=Sum('total_price'),
        total_bookings=Count('id'),
    )
    total_revenue = agg['total_revenue'] or 0
    total_bookings = agg['total_bookings'] or 0

    cancelled_count = Booking.objects.filter(
        status='cancelled', check_in__gte=date_from, check_in__lte=date_to,
    ).count()
    all_closed = total_bookings + cancelled_count
    cancellation_rate = round(cancelled_count / all_closed * 100, 1) if all_closed else 0

    revenue_by_property = (
        confirmed_qs
        .values('room__property__name', 'room__property__id')
        .annotate(revenue=Sum('total_price'), count=Count('id'))
        .order_by('-revenue')
    )

    # Occupancy: confirmed booking-nights / (days_in_range * active_rooms_per_property)
    days_in_range = max((date_to - date_from).days, 1)
    property_rooms = {
        p['property']: p['room_count']
        for p in Room.objects.filter(is_active=True).values('property').annotate(room_count=Count('id'))
    }
    occupancy_by_property = []
    for row in revenue_by_property:
        prop_id = row['room__property__id']
        room_count = property_rooms.get(prop_id, 1)
        capacity_nights = days_in_range * room_count
        booked_nights = sum(
            (b.check_out - b.check_in).days
            for b in confirmed_qs.filter(room__property_id=prop_id).only('check_in', 'check_out')
        )
        occupancy_by_property.append({
            'name': row['room__property__name'],
            'revenue': row['revenue'],
            'count': row['count'],
            'occupancy': round(booked_nights / capacity_nights * 100, 1) if capacity_nights else 0,
        })

    return render(request, 'superadmin/analytics.html', {
        'total_revenue': total_revenue,
        'total_bookings': total_bookings,
        'cancellation_rate': cancellation_rate,
        'occupancy_by_property': occupancy_by_property,
        'date_from': date_from,
        'date_to': date_to,
        'today': today,
    })


# ── Tax Config ─────────────────────────────────────────────────────────────────

@require_super_admin
def tax_config(request):
    properties = Property.objects.filter(is_active=True).prefetch_related('tax_config')
    if request.method == 'POST':
        prop_id = request.POST.get('property_id')
        prop = get_object_or_404(Property, pk=prop_id)
        cfg, _ = PropertyTaxConfig.objects.get_or_create(property=prop)
        cfg.threshold = Decimal(request.POST.get('threshold', '7500'))
        cfg.low_rate_pct = Decimal(request.POST.get('low_rate_pct', '12'))
        cfg.high_rate_pct = Decimal(request.POST.get('high_rate_pct', '18'))
        cfg.updated_by = request.user
        cfg.save()
        _log(request, 'TAX_CONFIG_UPDATED', detail=f"property={prop.name}")
        return redirect('superadmin:tax-config')
    return render(request, 'superadmin/tax_config.html', {'properties': properties})


# ── Loyalty Config ─────────────────────────────────────────────────────────────

@require_super_admin
def loyalty_config(request):
    from loyalty.models import LoyaltyConfig, LoyaltyTier, CampaignRule
    properties = Property.objects.filter(is_active=True).prefetch_related('loyalty_config')
    tiers = LoyaltyTier.objects.all()
    campaigns = CampaignRule.objects.all()[:20]
    configs = {c.property_id: c for c in LoyaltyConfig.objects.all()}

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'save_config':
            prop_id = request.POST.get('property_id')
            prop = get_object_or_404(Property, pk=prop_id)
            cfg, _ = LoyaltyConfig.objects.get_or_create(property=prop)
            cfg.first_booking_pts = int(request.POST.get('first_booking_pts', 200))
            cfg.pts_per_night = int(request.POST.get('pts_per_night', 100))
            cfg.monthly_repeat_multiplier = Decimal(request.POST.get('monthly_repeat_multiplier', '1.5'))
            cfg.save()
            _log(request, 'LOYALTY_CONFIG_UPDATED', detail=f"property={prop.name}")

        elif action == 'save_tier':
            tier_id = request.POST.get('tier_id')
            name = request.POST.get('name', '').strip()
            min_pts = int(request.POST.get('min_pts', 0))
            discount = Decimal(request.POST.get('discount_pct', '0'))
            sort_order = int(request.POST.get('sort_order', 0))
            if tier_id:
                LoyaltyTier.objects.filter(pk=tier_id).update(
                    name=name, min_pts=min_pts, discount_pct=discount, sort_order=sort_order)
            else:
                LoyaltyTier.objects.create(
                    name=name, min_pts=min_pts, discount_pct=discount, sort_order=sort_order)

        elif action == 'delete_tier':
            LoyaltyTier.objects.filter(pk=request.POST.get('tier_id')).delete()

        elif action == 'save_campaign':
            CampaignRule.objects.create(
                name=request.POST.get('name'),
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                multiplier=Decimal(request.POST.get('multiplier', '1')),
                is_active=True,
            )

        elif action == 'delete_campaign':
            CampaignRule.objects.filter(pk=request.POST.get('campaign_id')).delete()

        return redirect('superadmin:loyalty-config')

    return render(request, 'superadmin/loyalty_config.html', {
        'properties': properties,
        'tiers': tiers,
        'campaigns': campaigns,
        'configs': configs,
    })


# ── Rooms ──────────────────────────────────────────────────────────────────────

@require_super_admin
def rooms_list(request):
    property_filter = request.GET.get('property', '')
    rooms = Room.objects.select_related('property').order_by('property__name', 'name')
    if property_filter:
        rooms = rooms.filter(property_id=property_filter)
    properties = Property.objects.filter(is_active=True).order_by('name')
    return render(request, 'superadmin/rooms.html', {
        'rooms': rooms,
        'properties': properties,
        'property_filter': property_filter,
        'operational_choices': Room.OPERATIONAL_STATUS_CHOICES,
    })


@require_super_admin
@require_POST
def room_update(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    data = json.loads(request.body)
    action = data.get('action')

    if action == 'set_status':
        new_status = data.get('operational_status', '')
        valid = {s for s, _ in Room.OPERATIONAL_STATUS_CHOICES}
        if new_status not in valid:
            return JsonResponse({'error': 'Invalid status.'}, status=400)
        room.operational_status = new_status
        room.save(update_fields=['operational_status'])
        _log(request, 'ROOM_STATUS_UPDATED', detail=f"room={room.name}, status={new_status}")
        return JsonResponse({'message': f'Status set to {new_status}.'})

    if action == 'toggle_active':
        room.is_active = not room.is_active
        room.save(update_fields=['is_active'])
        state = 'activated' if room.is_active else 'deactivated'
        _log(request, 'ROOM_UPDATED', detail=f"room={room.name}, {state}")
        return JsonResponse({'message': f'Room {state}.', 'is_active': room.is_active})

    if action == 'update_details':
        fields_changed = []
        for field in ('name', 'room_type', 'price_per_night', 'capacity', 'amenities', 'description'):
            val = data.get(field)
            if val is not None:
                if field == 'price_per_night':
                    val = Decimal(str(val))
                elif field == 'capacity':
                    val = int(val)
                setattr(room, field, val)
                fields_changed.append(field)
        prop_id = data.get('property_id')
        if prop_id:
            room.property = get_object_or_404(Property, pk=prop_id)
            fields_changed.append('property')
        if fields_changed:
            room.save()
            _log(request, 'ROOM_UPDATED', detail=f"room={room.name}, fields={fields_changed}")
        return JsonResponse({'message': 'Room updated.'})

    return JsonResponse({'error': 'Unknown action.'}, status=400)


# ── Audit Log ──────────────────────────────────────────────────────────────────

@require_super_admin
def audit_log(request):
    logs = AuditLog.objects.select_related('actor', 'target_user').order_by('-created_at')
    action_filter = request.GET.get('action')
    if action_filter:
        logs = logs.filter(action=action_filter)
    return render(request, 'superadmin/audit_log.html', {
        'logs': logs[:100],
        'action_choices': AuditLog.ACTION_CHOICES,
        'selected_action': action_filter,
    })


# ── Bookings (all) ─────────────────────────────────────────────────────────────

@require_super_admin
def bookings_list(request):
    qs = Booking.objects.select_related('user', 'room__property').order_by('-check_in')

    status_filter = request.GET.get('status', '')
    property_filter = request.GET.get('property', '')
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')
    q = request.GET.get('q', '').strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if property_filter:
        qs = qs.filter(room__property_id=property_filter)
    if date_from:
        qs = qs.filter(check_in__gte=date_from)
    if date_to:
        qs = qs.filter(check_in__lte=date_to)
    if q:
        qs = qs.filter(
            Q(user__full_name__icontains=q) |
            Q(user__email__icontains=q) |
            Q(booking_reference__icontains=q)
        )

    properties = Property.objects.filter(is_active=True).order_by('name')
    return render(request, 'superadmin/bookings.html', {
        'bookings': qs[:200],
        'properties': properties,
        'status_choices': Booking.STATUS_CHOICES,
        'status_filter': status_filter,
        'property_filter': property_filter,
        'date_from': date_from,
        'date_to': date_to,
        'q': q,
    })


@require_super_admin
@require_POST
def booking_cancel(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    if booking.status not in ('confirmed', 'pending'):
        return JsonResponse({'error': 'Only confirmed or pending bookings can be cancelled.'}, status=400)
    reason = request.POST.get('reason', '').strip() or 'Cancelled by super admin'
    booking.status = 'cancelled'
    booking.save(update_fields=['status'])
    _log(request, 'BOOKING_CANCELLED', target_user=booking.user,
         detail=f"booking={booking.booking_reference}, reason={reason}")
    return JsonResponse({'message': 'Booking cancelled.'})


@require_super_admin
@require_POST
def booking_complete(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    if booking.status != 'confirmed':
        return JsonResponse({'error': 'Only confirmed bookings can be marked completed.'}, status=400)
    booking.status = 'completed'
    booking.save(update_fields=['status'])
    _log(request, 'BOOKING_COMPLETED', target_user=booking.user,
         detail=f"booking={booking.booking_reference}")
    return JsonResponse({'message': 'Booking marked as completed.'})


# ── Guests & Loyalty ──────────────────────────────────────────────────────────

@require_super_admin
def guests_list(request):
    from accounts.models import UserProfile
    q = request.GET.get('q', '').strip()

    guests = User.objects.filter(
        userprofile__role='guest'
    ).select_related('userprofile').order_by('-date_joined')

    if q:
        guests = guests.filter(
            Q(full_name__icontains=q) | Q(email__icontains=q)
        )

    guest_data = []
    for u in guests[:100]:
        profile = u.userprofile
        booking_count = Booking.objects.filter(user=u, status__in=('confirmed', 'completed')).count()
        guest_data.append({
            'user': u,
            'profile': profile,
            'booking_count': booking_count,
        })

    return render(request, 'superadmin/guests.html', {
        'guests': guest_data,
        'q': q,
    })


@require_super_admin
@require_POST
def loyalty_adjust(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    data = json.loads(request.body)
    amount = int(data.get('amount', 0))
    reason = data.get('reason', '').strip() or 'Manual adjustment'

    if amount == 0:
        return JsonResponse({'error': 'Amount cannot be zero.'}, status=400)

    profile = target.userprofile
    profile.loyalty_points = max(0, profile.loyalty_points + amount)
    profile.save(update_fields=['loyalty_points'])
    profile.recalculate_tier()

    action = 'LOYALTY_CREDIT' if amount > 0 else 'LOYALTY_DEBIT'
    _log(request, action, target_user=target,
         detail=f"amount={amount}, reason={reason}, new_balance={profile.loyalty_points}")

    return JsonResponse({
        'message': f'Points adjusted by {amount:+d}. New balance: {profile.loyalty_points}.',
        'loyalty_points': profile.loyalty_points,
        'loyalty_tier': profile.loyalty_tier,
    })


# ── Property CRUD ──────────────────────────────────────────────────────────────

@require_super_admin
def properties_list(request):
    properties = Property.objects.annotate(
        room_count=Count('rooms'),
    ).order_by('name')
    return render(request, 'superadmin/properties.html', {
        'properties': properties,
    })


@require_super_admin
@require_POST
def property_create(request):
    name = request.POST.get('name', '').strip()
    city = request.POST.get('city', '').strip()
    address = request.POST.get('address', '').strip()
    whatsapp = request.POST.get('whatsapp_number', '').strip()

    if not name or not city:
        return JsonResponse({'error': 'Name and city are required.'}, status=400)

    prop = Property.objects.create(
        name=name, city=city, address=address, whatsapp_number=whatsapp,
    )
    _log(request, 'PROPERTY_CREATED', detail=f"property={prop.name}, city={city}")
    return JsonResponse({'message': f'Property "{prop.name}" created.', 'id': str(prop.id)})


@require_super_admin
@require_POST
def property_update(request, property_id):
    prop = get_object_or_404(Property, pk=property_id)
    data = json.loads(request.body)
    action = data.get('action')

    if action == 'toggle_active':
        prop.is_active = not prop.is_active
        prop.save(update_fields=['is_active'])
        state = 'activated' if prop.is_active else 'deactivated'
        _log(request, 'PROPERTY_UPDATED', detail=f"property={prop.name}, {state}")
        return JsonResponse({'message': f'Property {state}.', 'is_active': prop.is_active})

    if action == 'update_details':
        for field in ('name', 'city', 'address', 'whatsapp_number'):
            val = data.get(field)
            if val is not None:
                setattr(prop, field, val.strip() if isinstance(val, str) else val)
        prop.save()
        _log(request, 'PROPERTY_UPDATED', detail=f"property={prop.name}")
        return JsonResponse({'message': 'Property updated.'})

    return JsonResponse({'error': 'Unknown action.'}, status=400)


# ── Room Create ────────────────────────────────────────────────────────────────

@require_super_admin
@require_POST
def room_create(request):
    property_id = request.POST.get('property_id')
    name = request.POST.get('name', '').strip()
    room_type = request.POST.get('room_type', 'single')
    price = request.POST.get('price_per_night', '0')
    capacity = request.POST.get('capacity', '2')
    amenities = request.POST.get('amenities', '').strip()
    description = request.POST.get('description', '').strip()

    if not property_id or not name:
        return JsonResponse({'error': 'Property and room name are required.'}, status=400)

    prop = get_object_or_404(Property, pk=property_id)
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
    _log(request, 'ROOM_CREATED', detail=f"room={room.name}, property={prop.name}")
    return JsonResponse({'message': f'Room "{room.name}" created.', 'id': str(room.id)})


# ── Room Image Management ─────────────────────────────────────────────────────

@require_super_admin
def room_images(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    images = room.images.all().order_by('order', '-is_primary')
    return render(request, 'superadmin/room_images.html', {
        'room': room,
        'images': images,
    })


@require_super_admin
@require_POST
def room_image_upload(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'No image file provided.'}, status=400)

    caption = request.POST.get('caption', '').strip()
    is_primary = request.POST.get('is_primary') == 'on'

    if is_primary:
        room.images.filter(is_primary=True).update(is_primary=False)

    img = RoomImage.objects.create(
        room=room, image=image_file, caption=caption, is_primary=is_primary,
        order=room.images.count(),
    )
    _log(request, 'ROOM_IMAGE_UPLOADED', detail=f"room={room.name}, image={img.id}")
    return JsonResponse({'message': 'Image uploaded.', 'id': str(img.id)})


@require_super_admin
@require_POST
def room_image_delete(request, image_id):
    img = get_object_or_404(RoomImage, pk=image_id)
    room_name = img.room.name
    img.image.delete(save=False)
    img.delete()
    _log(request, 'ROOM_IMAGE_DELETED', detail=f"room={room_name}")
    return JsonResponse({'message': 'Image deleted.'})


@require_super_admin
@require_POST
def room_image_set_primary(request, image_id):
    img = get_object_or_404(RoomImage, pk=image_id)
    img.room.images.filter(is_primary=True).update(is_primary=False)
    img.is_primary = True
    img.save(update_fields=['is_primary'])
    return JsonResponse({'message': 'Set as primary image.'})
