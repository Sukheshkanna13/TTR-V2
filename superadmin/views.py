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

from rooms.models import Booking, Room, Property
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


# ── Employee CRUD ──────────────────────────────────────────────────────────────

@require_super_admin
def employees_list(request):
    employees = User.objects.filter(
        userprofile__role='employee_admin'
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
    profile.role = 'employee_admin'
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
