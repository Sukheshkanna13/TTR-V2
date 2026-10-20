import datetime as dt
import logging
import secrets
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from rooms.models import Booking, Room, RoomImage, Property
from .decorators import require_super_admin
from .models import AuditLog, PropertyTaxConfig

from accounts.models import User
from accounts.role_routing import EMPLOYEE_ADMIN_ROLES
from core.admin_utils import (
    BadInput, audit, clean_date, clean_uuid, parse_json, to_date, to_decimal, to_int,
)
from core.constants import UNKNOWN_ACTION_ERR, REQ_TO_BOOK

logger = logging.getLogger(__name__)

# Bookings that represent real, paid stays. Operational counters (active stays,
# arrivals, departures) deliberately stay confirmed-only.
REVENUE_STATUSES = ('confirmed', 'completed')

# Model field limits (PositiveSmallIntegerField / DecimalField(max_digits=10, 2)).
MAX_SMALL_INT = 32767
MAX_MONEY = Decimal('99999999.99')
MAX_BIG_MONEY = Decimal('9999999999.99')   # DecimalField(max_digits=12, decimal_places=2)
ARI_HORIZON_DAYS = 500


def _log(request, action, target_user=None, detail=''):
    audit(request, action, target_user=target_user, detail=detail)


def _push_ari(room_type, property_id, change_types):
    """Queue an OTA push for every night from today over the booking horizon."""
    from core.ota.dispatch import record_ari_change
    today = date.today()
    record_ari_change(
        room_type, property_id, today, today + timedelta(days=ARI_HORIZON_DAYS),
        change_types=change_types,
    )


def _text(value, field, max_len=None, required=False):
    """Coerce a client-supplied text field; reject non-strings instead of 500-ing on save."""
    if not isinstance(value, str):
        raise BadInput(f'{field} must be text.')
    value = value.strip()
    if required and not value:
        raise BadInput(f'{field} is required.')
    if max_len and len(value) > max_len:
        raise BadInput(f'{field} must be at most {max_len} characters.')
    return value


def _uuid_list(values, field):
    if not isinstance(values, (list, tuple)):
        raise BadInput(f'{field} must be a list.')
    cleaned = []
    for v in values:
        cv = clean_uuid(v)
        if cv is None:
            raise BadInput(f'Invalid id in {field}.')
        cleaned.append(cv)
    return cleaned


# ── Dashboard ──────────────────────────────────────────────────────────────────

def _collected_today():
    """Money actually collected today: captured payments created today (local time)."""
    from payments.models import Payment
    tz_today = timezone.localdate()
    start = timezone.make_aware(dt.datetime.combine(tz_today, dt.time.min))
    end = start + timedelta(days=1)
    return Payment.objects.filter(
        status='captured', created_at__gte=start, created_at__lt=end,
    ).aggregate(t=Sum('amount'))['t'] or 0


@require_super_admin
def dashboard(request):
    today = timezone.now().date()
    month_start = today.replace(day=1)

    active_bookings = Booking.objects.filter(
        status='confirmed', check_in__lte=today, check_out__gt=today,
    ).count()

    todays_arrivals_qs = Booking.objects.filter(
        status='confirmed', check_in=today,
    )
    todays_arrivals = list(todays_arrivals_qs.select_related('user', 'room__property'))

    todays_departures = list(Booking.objects.filter(
        status='confirmed', check_out=today,
    ).select_related('user', 'room__property'))

    pending_holds = list(Booking.objects.filter(
        status='pending',
    ).select_related('user', 'room__property').order_by('created_at')[:20])

    today_revenue = _collected_today()

    month_revenue = Booking.objects.filter(
        status__in=REVENUE_STATUSES, check_in__gte=month_start,
    ).aggregate(t=Sum('total_price'))['t'] or 0

    total_rooms = Room.objects.filter(is_active=True).count()
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
@require_GET
def dashboard_live_data(request):
    today = timezone.now().date()

    active_bookings = Booking.objects.filter(
        status='confirmed', check_in__lte=today, check_out__gt=today,
    ).count()

    todays_checkins = Booking.objects.filter(
        status='confirmed', check_in=today,
    ).count()

    todays_checkouts = Booking.objects.filter(
        status='confirmed', check_out=today,
    ).count()

    today_revenue = _collected_today()

    pending_qs = Booking.objects.filter(
        status='pending',
    ).select_related('user', 'room__property').order_by('created_at')[:20]

    pending_holds = []
    for b in pending_qs:
        reference = b.booking_reference or str(b.id)
        if getattr(b, 'user', None):
            guest = b.user.full_name or b.user.email
        else:
            guest = '(deleted)'
        room_name = b.room.name
        property_name = b.room.property.name if b.room.property else ''
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
    employees_qs = User.objects.filter(
        userprofile__role__in=EMPLOYEE_ADMIN_ROLES
    ).select_related(
        'userprofile', 'userprofile__created_by'
    ).prefetch_related('userprofile__assigned_properties').order_by('-date_joined')

    paginator = Paginator(employees_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    properties = Property.objects.filter(is_active=True)
    return render(request, 'superadmin/employees.html', {
        'employees': page_obj,
        'page_obj': page_obj,
        'properties': properties,
    })


@require_super_admin
@require_POST
def employee_create(request):
    email = request.POST.get('email', '').strip().lower()
    full_name = request.POST.get('full_name', '').strip()
    fin_level = request.POST.get('fin_level', 'C')
    if fin_level not in ('A', 'B', 'C'):
        fin_level = 'C'
    try:
        property_ids = _uuid_list(request.POST.getlist('properties'), 'properties')
    except BadInput as e:
        return e.response()

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
    profile.created_by = request.user
    profile.save()
    if property_ids:
        profile.assigned_properties.set(Property.objects.filter(id__in=property_ids))

    _log(request, 'EMPLOYEE_CREATED', target_user=user,
         detail=f"fin_level={fin_level}, properties={property_ids}")

    return JsonResponse({
        'message': f'Employee created. Temp password: {temp_password}',
        'temp_password': temp_password,
    })


def _emp_revoke(request, employee, data):
    if hasattr(employee, 'userprofile'):
        employee.userprofile.revoke(request.user)
    else:
        employee.is_active = False
        employee.save(update_fields=['is_active'])
    _log(request, 'EMPLOYEE_REVOKED', target_user=employee)
    return JsonResponse({'message': 'Employee revoked. Access removed.'})

def _emp_reinstate(request, employee, data):
    if hasattr(employee, 'userprofile'):
        employee.userprofile.reinstate()
    else:
        employee.is_active = True
        employee.save(update_fields=['is_active'])
    _log(request, 'EMPLOYEE_UNLOCKED', target_user=employee, detail='reinstated from revoked')
    return JsonResponse({'message': 'Employee reinstated.'})

def _emp_lock(request, employee, data):
    employee.is_active = False
    employee.save(update_fields=['is_active'])
    _log(request, 'EMPLOYEE_LOCKED', target_user=employee)
    return JsonResponse({'message': 'Account locked.'})

def _emp_unlock(request, employee, data):
    employee.is_active = True
    employee.save(update_fields=['is_active'])
    _log(request, 'EMPLOYEE_UNLOCKED', target_user=employee)
    return JsonResponse({'message': 'Account unlocked.'})

def _emp_reset_password(request, employee, data):
    temp = secrets.token_urlsafe(12)
    employee.set_password(temp)
    employee.save()
    if hasattr(employee, 'userprofile'):
        employee.userprofile.must_change_password = True
        employee.userprofile.save(update_fields=['must_change_password'])
    _log(request, 'PASSWORD_RESET', target_user=employee)
    return JsonResponse({'message': f'Password reset. New temp: {temp}', 'temp_password': temp})

def _emp_update_fin(request, employee, data):
    fin = data.get('fin_level', 'C')
    if fin not in ('A', 'B', 'C'):
        fin = 'C'
    if hasattr(employee, 'userprofile'):
        employee.userprofile.fin_level = fin
        employee.userprofile.save(update_fields=['fin_level'])
    _log(request, 'EMPLOYEE_UPDATED', target_user=employee, detail=f"fin_level→{fin}")
    return JsonResponse({'message': 'Financial level updated.'})

def _emp_update_properties(request, employee, data):
    prop_ids = _uuid_list(data.get('property_ids', []), 'property_ids')
    if hasattr(employee, 'userprofile'):
        employee.userprofile.assigned_properties.set(
            Property.objects.filter(id__in=prop_ids)
        )
    _log(request, 'EMPLOYEE_UPDATED', target_user=employee, detail=f"properties={prop_ids}")
    return JsonResponse({'message': 'Properties updated.'})

@require_super_admin
@require_POST
def employee_update(request, user_id):
    employee = get_object_or_404(User, pk=user_id)
    try:
        data = parse_json(request)
    except BadInput as e:
        return e.response()
    action = data.get('action')

    if employee == request.user and action in ('lock', 'revoke'):
        return JsonResponse({'error': 'You cannot disable your own account.'}, status=400)

    profile = getattr(employee, 'userprofile', None)
    if profile is None or profile.role not in EMPLOYEE_ADMIN_ROLES:
        return JsonResponse({'error': 'Cannot manage non-employee users.'}, status=403)

    handlers = {
        'revoke': _emp_revoke,
        'reinstate': _emp_reinstate,
        'lock': _emp_lock,
        'unlock': _emp_unlock,
        'reset_password': _emp_reset_password,
        'update_fin': _emp_update_fin,
        'update_properties': _emp_update_properties,
    }

    handler = handlers.get(action)
    if handler:
        try:
            return handler(request, employee, data)
        except BadInput as e:
            return e.response()

    return JsonResponse({'error': UNKNOWN_ACTION_ERR}, status=400)


@require_super_admin
@require_POST
def employee_delete(request, user_id):
    """Permanently delete an employee — only allowed if the account was never used."""
    employee = get_object_or_404(User, pk=user_id)

    if employee == request.user:
        return JsonResponse({'error': 'You cannot delete your own account.'}, status=400)

    profile = getattr(employee, 'userprofile', None)
    if profile is None or profile.role not in EMPLOYEE_ADMIN_ROLES:
        return JsonResponse({'error': 'Cannot delete non-employee users.'}, status=403)
    if not profile.can_hard_delete:
        return JsonResponse(
            {'error': 'Account has activity — revoke instead of deleting.'},
            status=400,
        )

    # Log before deletion: AuditLog.target_user is SET_NULL, so capture identity now.
    _log(request, 'EMPLOYEE_DELETED', target_user=employee,
         detail=f"email={employee.email}, name={employee.full_name}")
    employee.delete()
    return JsonResponse({'message': 'Employee permanently deleted.'})


# ── Analytics ──────────────────────────────────────────────────────────────────

@require_super_admin
def analytics(request):
    today = timezone.now().date()

    date_from = clean_date(request.GET.get('from')) or today.replace(day=1)
    date_to = clean_date(request.GET.get('to')) or today
    range_swapped = date_from > date_to
    if range_swapped:
        date_from, date_to = date_to, date_from

    # Revenue, counts and the cancellation rate are attributed to the check-in date.
    counted_qs = Booking.objects.filter(
        status__in=REVENUE_STATUSES, check_in__gte=date_from, check_in__lte=date_to,
    )

    agg = counted_qs.aggregate(
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

    revenue_rows = list(
        counted_qs
        .values('room__property__name', 'room__property__id')
        .annotate(revenue=Sum('total_price'), count=Count('id'))
        .order_by('-revenue')
    )

    # Occupancy: nights actually inside [date_from, date_to] / (days * active rooms).
    days_in_range = (date_to - date_from).days + 1
    range_end = date_to + timedelta(days=1)  # exclusive
    property_rooms = {
        p['property']: p['room_count']
        for p in Room.objects.filter(is_active=True).values('property').annotate(room_count=Count('id'))
    }
    booked_nights = defaultdict(int)
    overlapping = Booking.objects.filter(
        status__in=REVENUE_STATUSES, check_in__lte=date_to, check_out__gt=date_from,
    ).values_list('room__property_id', 'check_in', 'check_out')
    for prop_id, check_in, check_out in overlapping:
        nights = (min(check_out, range_end) - max(check_in, date_from)).days
        if nights > 0:
            booked_nights[prop_id] += nights

    rows = {}
    for row in revenue_rows:
        rows[row['room__property__id']] = {
            'name': row['room__property__name'] or 'Unassigned',
            'revenue': row['revenue'],
            'count': row['count'],
        }
    missing = [pid for pid in booked_nights if pid not in rows]
    if missing:
        names = dict(Property.objects.filter(pk__in=[m for m in missing if m]).values_list('pk', 'name'))
        for pid in missing:
            rows[pid] = {'name': names.get(pid, 'Unassigned'), 'revenue': 0, 'count': 0}

    occupancy_by_property = []
    for prop_id, row in rows.items():
        capacity_nights = days_in_range * property_rooms.get(prop_id, 0)
        occupancy = 0
        if capacity_nights:
            occupancy = min(round(booked_nights.get(prop_id, 0) / capacity_nights * 100, 1), 100.0)
        occupancy_by_property.append({**row, 'occupancy': occupancy})

    return render(request, 'superadmin/analytics.html', {
        'total_revenue': total_revenue,
        'total_bookings': total_bookings,
        'cancellation_rate': cancellation_rate,
        'occupancy_by_property': occupancy_by_property,
        'date_from': date_from,
        'date_to': date_to,
        'range_swapped': range_swapped,
        'today': today,
    })


# ── Tax Config ─────────────────────────────────────────────────────────────────

def _parse_tax_form(post):
    threshold = to_decimal(post.get('threshold', '7500'), 'threshold', min_value=0, max_value=MAX_MONEY)
    low = to_decimal(post.get('low_rate_pct', '12'), 'low rate', min_value=0, max_value=28)
    high = to_decimal(post.get('high_rate_pct', '18'), 'high rate', min_value=0, max_value=28)
    if low > high:
        raise BadInput('Low rate cannot be higher than the high rate.')
    return threshold, low, high


@require_super_admin
def tax_config(request):
    properties = Property.objects.filter(is_active=True).prefetch_related('tax_config')
    if request.method == 'POST':
        prop_id = clean_uuid(request.POST.get('property_id'))
        if prop_id is None:
            messages.error(request, 'Choose a valid property.')
            return redirect('superadmin:tax-config')
        prop = get_object_or_404(Property, pk=prop_id)
        try:
            threshold, low, high = _parse_tax_form(request.POST)
        except BadInput as e:
            messages.error(request, f'Tax config not saved: {e.message}')
            return redirect('superadmin:tax-config')
        cfg, _ = PropertyTaxConfig.objects.get_or_create(property=prop)
        old = (cfg.threshold, cfg.low_rate_pct, cfg.high_rate_pct)
        cfg.threshold, cfg.low_rate_pct, cfg.high_rate_pct = threshold, low, high
        cfg.updated_by = request.user
        cfg.save()
        _log(request, 'TAX_CONFIG_UPDATED', detail=(
            f"property={prop.name}, threshold {old[0]}→{threshold}, "
            f"low {old[1]}→{low}, high {old[2]}→{high}"))
        messages.success(request, 'Tax config saved.')
        return redirect('superadmin:tax-config')
    return render(request, 'superadmin/tax_config.html', {'properties': properties})


# ── Loyalty Config ─────────────────────────────────────────────────────────────
# Handlers raise BadInput on malformed input; loyalty_config turns that into a
# flash message + redirect (the page is a plain form POST, not a fetch).

def _post_property(request, field='property_id'):
    prop_id = clean_uuid(request.POST.get(field))
    if prop_id is None:
        raise BadInput('Choose a valid property.')
    return get_object_or_404(Property, pk=prop_id)


def _handle_save_config(request):
    from loyalty.models import LoyaltyConfig
    prop = _post_property(request)
    first_pts = to_int(request.POST.get('first_booking_pts', 200), 'first booking points',
                       min_value=0, max_value=1_000_000)
    per_night = to_int(request.POST.get('pts_per_night', 100), 'points per night',
                       min_value=0, max_value=1_000_000)
    multiplier = to_decimal(request.POST.get('monthly_repeat_multiplier', '1.5'),
                            'monthly repeat multiplier', min_value=0, max_value='99.99')
    cfg, _ = LoyaltyConfig.objects.get_or_create(property=prop)
    old = (cfg.first_booking_pts, cfg.pts_per_night, cfg.monthly_repeat_multiplier)
    cfg.first_booking_pts = first_pts
    cfg.pts_per_night = per_night
    cfg.monthly_repeat_multiplier = multiplier
    cfg.save()
    _log(request, 'LOYALTY_CONFIG_UPDATED', detail=(
        f"property={prop.name}, first_booking_pts {old[0]}→{first_pts}, "
        f"pts_per_night {old[1]}→{per_night}, multiplier {old[2]}→{multiplier}"))


def _handle_save_tier(request):
    from loyalty.models import LoyaltyTier
    tier_id = request.POST.get('tier_id')
    name = _text(request.POST.get('name', ''), 'Tier name', max_len=50, required=True)
    min_pts = to_int(request.POST.get('min_pts', 0), 'minimum points', min_value=0, max_value=100_000_000)
    discount = to_decimal(request.POST.get('discount_pct', '0'), 'discount %', min_value=0, max_value=100)
    sort_order = to_int(request.POST.get('sort_order', 0), 'sort order', min_value=0, max_value=MAX_SMALL_INT)
    if tier_id:
        tier_id = to_int(tier_id, 'tier id')
    clash = LoyaltyTier.objects.filter(name=name)
    if tier_id:
        clash = clash.exclude(pk=tier_id)
    if clash.exists():
        raise BadInput(f'A tier named "{name}" already exists.')
    if tier_id:
        LoyaltyTier.objects.filter(pk=tier_id).update(
            name=name, min_pts=min_pts, discount_pct=discount, sort_order=sort_order)
    else:
        LoyaltyTier.objects.create(
            name=name, min_pts=min_pts, discount_pct=discount, sort_order=sort_order)
    _log(request, 'LOYALTY_TIER_SAVED', detail=(
        f"tier={name}, min_pts={min_pts}, discount_pct={discount}, sort_order={sort_order}"
        + (f", tier_id={tier_id}" if tier_id else ", created")))


def _handle_delete_tier(request):
    from loyalty.models import LoyaltyTier
    tier_id = to_int(request.POST.get('tier_id'), 'tier id')
    tier = LoyaltyTier.objects.filter(pk=tier_id).first()
    if tier is None:
        return
    detail = f"tier={tier.name}, min_pts={tier.min_pts}, discount_pct={tier.discount_pct}"
    tier.delete()
    _log(request, 'LOYALTY_TIER_DELETED', detail=detail)


def _handle_save_campaign(request):
    from loyalty.models import CampaignRule
    name = _text(request.POST.get('name', ''), 'Campaign name', max_len=100, required=True)
    start = to_date(request.POST.get('start_date', ''), 'start date')
    end = to_date(request.POST.get('end_date', ''), 'end date')
    if end < start:
        raise BadInput('Campaign end date cannot be before the start date.')
    multiplier = to_decimal(request.POST.get('multiplier', '1'), 'multiplier',
                            min_value=0, max_value='99.99')
    CampaignRule.objects.create(
        name=name, start_date=start, end_date=end, multiplier=multiplier, is_active=True,
    )
    _log(request, 'LOYALTY_CAMPAIGN_SAVED',
         detail=f"campaign={name}, {start}..{end}, multiplier={multiplier}")


def _handle_delete_campaign(request):
    from loyalty.models import CampaignRule
    campaign_id = to_int(request.POST.get('campaign_id'), 'campaign id')
    campaign = CampaignRule.objects.filter(pk=campaign_id).first()
    if campaign is None:
        return
    detail = f"campaign={campaign.name}, {campaign.start_date}..{campaign.end_date}"
    campaign.delete()
    _log(request, 'LOYALTY_CAMPAIGN_DELETED', detail=detail)


def _handle_save_redemption_rule(request):
    from loyalty.models import CouponRedemptionRule
    rule_id = clean_uuid(request.POST.get('rule_id')) if request.POST.get('rule_id') else None
    if request.POST.get('rule_id') and rule_id is None:
        raise BadInput('Invalid rule id.')
    name = _text(request.POST.get('name', ''), 'Rule name', max_len=100)
    points_cost = to_int(request.POST.get('points_cost', 100), 'points cost',
                         min_value=1, max_value=100_000_000)
    discount_type = request.POST.get('discount_type', 'fixed')
    if discount_type not in ('fixed', 'percentage'):
        raise BadInput('Invalid discount type.')
    discount_value = to_decimal(request.POST.get('discount_value', '0.00'), 'discount value',
                                min_value=0, max_value=100 if discount_type == 'percentage' else MAX_MONEY)
    min_booking_amount = to_decimal(request.POST.get('min_booking_amount', '0.00'),
                                    'minimum booking amount', min_value=0, max_value=MAX_MONEY)
    max_discount_str = request.POST.get('max_discount_amount', '').strip()
    max_discount_amount = (
        to_decimal(max_discount_str, 'max discount amount', min_value=0, max_value=MAX_MONEY)
        if max_discount_str else None
    )
    validity_days = to_int(request.POST.get('validity_days', 30), 'validity days',
                           min_value=1, max_value=3650)
    prop_id = request.POST.get('property_id') or None
    if prop_id:
        prop_id = clean_uuid(prop_id)
        if prop_id is None:
            raise BadInput('Invalid property.')
    prop = Property.objects.filter(pk=prop_id).first() if prop_id else None

    if rule_id:
        CouponRedemptionRule.objects.filter(pk=rule_id).update(
            name=name,
            points_cost=points_cost,
            discount_type=discount_type,
            discount_value=discount_value,
            min_booking_amount=min_booking_amount,
            max_discount_amount=max_discount_amount,
            validity_days=validity_days,
            property=prop,
        )
    else:
        CouponRedemptionRule.objects.create(
            name=name,
            points_cost=points_cost,
            discount_type=discount_type,
            discount_value=discount_value,
            min_booking_amount=min_booking_amount,
            max_discount_amount=max_discount_amount,
            validity_days=validity_days,
            property=prop,
            is_active=True,
        )
    _log(request, 'REDEMPTION_RULE_SAVED', detail=f"name={name}, pts={points_cost}")


def _handle_delete_redemption_rule(request):
    from loyalty.models import CouponRedemptionRule
    rule_id = clean_uuid(request.POST.get('rule_id'))
    if rule_id is None:
        raise BadInput('Invalid rule id.')
    CouponRedemptionRule.objects.filter(pk=rule_id).delete()
    _log(request, 'REDEMPTION_RULE_DELETED', detail=f"rule_id={rule_id}")


def _handle_toggle_redemption_rule(request):
    from loyalty.models import CouponRedemptionRule
    rule_id = clean_uuid(request.POST.get('rule_id'))
    if rule_id is None:
        raise BadInput('Invalid rule id.')
    rule = CouponRedemptionRule.objects.filter(pk=rule_id).first()
    if rule:
        rule.is_active = not rule.is_active
        rule.save(update_fields=['is_active'])
        _log(request, 'REDEMPTION_RULE_TOGGLED', detail=f"rule_id={rule.id}, is_active={rule.is_active}")


@require_super_admin
def loyalty_config(request):
    from loyalty.models import LoyaltyConfig, LoyaltyTier, CampaignRule, CouponRedemptionRule, Coupon
    properties = Property.objects.filter(is_active=True).prefetch_related('loyalty_config')
    tiers = LoyaltyTier.objects.all()
    campaigns = CampaignRule.objects.all()[:20]
    configs = {getattr(c, 'property_id'): c for c in LoyaltyConfig.objects.all()}
    redemption_rules = CouponRedemptionRule.objects.select_related('property').order_by('points_cost')
    recent_coupons = Coupon.objects.select_related('user', 'redemption_rule').order_by('-created_at')[:20]

    if request.method == 'POST':
        action = request.POST.get('action')
        handlers = {
            'save_config': _handle_save_config,
            'save_tier': _handle_save_tier,
            'delete_tier': _handle_delete_tier,
            'save_campaign': _handle_save_campaign,
            'delete_campaign': _handle_delete_campaign,
            'save_redemption_rule': _handle_save_redemption_rule,
            'delete_redemption_rule': _handle_delete_redemption_rule,
            'toggle_redemption_rule': _handle_toggle_redemption_rule,
        }
        handler = handlers.get(action)
        if handler:
            try:
                handler(request)
            except BadInput as e:
                messages.error(request, f'Not saved: {e.message}')
        return redirect('superadmin:loyalty-config')

    return render(request, 'superadmin/loyalty_config.html', {
        'properties': properties,
        'tiers': tiers,
        'campaigns': campaigns,
        'configs': configs,
        'redemption_rules': redemption_rules,
        'recent_coupons': recent_coupons,
    })


# ── Rooms ──────────────────────────────────────────────────────────────────────

@require_super_admin
def rooms_list(request):
    property_filter = clean_uuid(request.GET.get('property')) or ''
    rooms_qs = Room.objects.select_related('property').order_by('property__name', 'name')
    if property_filter:
        rooms_qs = rooms_qs.filter(property_id=property_filter)

    paginator = Paginator(rooms_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    properties = Property.objects.filter(is_active=True).order_by('name')
    return render(request, 'superadmin/rooms.html', {
        'rooms': page_obj,
        'page_obj': page_obj,
        'properties': properties,
        'property_filter': property_filter,
        'operational_choices': Room.OPERATIONAL_STATUS_CHOICES,
    })


def _clean_room_field(field, val):
    """Validate one editable Room field (shared by room_create and update_details)."""
    if field == 'name':
        return _text(val, 'Room name', max_len=100, required=True)
    if field == 'room_type':
        if not isinstance(val, str) or val not in dict(Room.ROOM_TYPE_CHOICES):
            raise BadInput('Invalid room type.')
        return val
    if field == 'price_per_night':
        return to_decimal(val, 'price', min_value='0.01', max_value=MAX_MONEY).quantize(Decimal('0.01'))
    if field == 'capacity':
        return to_int(val, 'capacity', min_value=1, max_value=20)
    if field == 'rating':
        if val in ('', None):
            return Decimal('4.5')
        return to_decimal(val, 'rating', min_value=0, max_value=5).quantize(Decimal('0.1'))
    return _text(val, field)   # amenities, description


def _room_set_status(request, room, data):
    new_status = data.get('operational_status', '')
    valid = {s for s, _ in Room.OPERATIONAL_STATUS_CHOICES}
    if new_status not in valid:
        return JsonResponse({'error': 'Invalid status.'}, status=400)
    room.operational_status = new_status
    room.save(update_fields=['operational_status'])
    _log(request, 'ROOM_STATUS_UPDATED', detail=f"room={room.name}, status={new_status}")
    # C7.3: status change affects availability for all future dates
    _push_ari(room.room_type, room.property_id, ("availability",))
    return JsonResponse({'message': f'Status set to {new_status}.'})

def _room_toggle_active(request, room, data):
    room.is_active = not room.is_active
    room.save(update_fields=['is_active'])
    state = 'activated' if room.is_active else 'deactivated'
    _log(request, 'ROOM_UPDATED', detail=f"room={room.name}, {state}")
    # An inactive room is excluded from inventory, so OTA availability changes.
    _push_ari(room.room_type, room.property_id, ("availability",))
    return JsonResponse({'message': f'Room {state}.', 'is_active': room.is_active})

def _room_toggle_featured(request, room, data):
    room.is_featured = not room.is_featured
    room.save(update_fields=['is_featured'])
    state = 'featured' if room.is_featured else 'unfeatured'
    _log(request, 'ROOM_UPDATED', detail=f"room={room.name}, {state}")
    return JsonResponse({'message': f'Room {state}.', 'is_featured': room.is_featured})

def _room_update_details(request, room, data):
    old_type, old_prop, old_price = room.room_type, room.property_id, room.price_per_night
    fields_changed = []
    for field in ('name', 'room_type', 'price_per_night', 'capacity', 'amenities', 'description', 'rating'):
        val = data.get(field)
        if val is None:
            continue
        setattr(room, field, _clean_room_field(field, val))
        fields_changed.append(field)
    prop_id = data.get('property_id')
    if prop_id:
        clean_prop_id = clean_uuid(prop_id)
        if clean_prop_id is None:
            raise BadInput('Invalid property.')
        room.property = get_object_or_404(Property, pk=clean_prop_id)
        fields_changed.append('property')
    if fields_changed:
        room.save()
        detail = f"room={room.name}, fields={fields_changed}"
        if 'price_per_night' in fields_changed:
            detail += f", price {old_price}→{room.price_per_night}"
        if room.room_type != old_type:
            detail += f", room_type {old_type}→{room.room_type}"
        if room.property_id != old_prop:
            detail += f", property {old_prop}→{room.property_id}"
        _log(request, 'ROOM_UPDATED', detail=detail)

        if room.room_type != old_type or room.property_id != old_prop:
            # Inventory moved between (room_type, property) buckets: refresh both.
            for room_type, property_id in {(old_type, old_prop), (room.room_type, room.property_id)}:
                _push_ari(room_type, property_id, ("availability", "rates"))
        elif 'price_per_night' in fields_changed:
            # C7.3: price change → push updated rates for all future dates
            _push_ari(room.room_type, room.property_id, ("rates",))
    return JsonResponse({'message': 'Room updated.'})

@require_super_admin
@require_POST
def room_update(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    try:
        data = parse_json(request)
    except BadInput as e:
        return e.response()
    action = data.get('action')

    handlers = {
        'set_status': _room_set_status,
        'toggle_active': _room_toggle_active,
        'toggle_featured': _room_toggle_featured,
        'update_details': _room_update_details,
    }

    handler = handlers.get(action)
    if handler:
        try:
            return handler(request, room, data)
        except BadInput as e:
            return e.response()

    return JsonResponse({'error': UNKNOWN_ACTION_ERR}, status=400)


@require_super_admin
@require_POST
def room_delete(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    if room.bookings.exists():
        return JsonResponse(
            {'error': 'This room has booking history and cannot be deleted. Deactivate it instead.'},
            status=400
        )
    room_name = room.name
    room_type, property_id = room.room_type, room.property_id
    property_name = room.property.name if room.property else 'Unknown Property'
    room.delete()
    _log(request, 'ROOM_DELETED', detail=f"room={room_name}, property={property_name}")
    _push_ari(room_type, property_id, ("availability",))
    return JsonResponse({'message': f'Room "{room_name}" successfully deleted.'})


# ── Audit Log ──────────────────────────────────────────────────────────────────

@require_super_admin
def audit_log(request):
    logs = AuditLog.objects.select_related('actor', 'target_user').order_by('-created_at')
    action_filter = request.GET.get('action')
    if action_filter:
        logs = logs.filter(action=action_filter)

    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'superadmin/audit_log.html', {
        'logs': page_obj,
        'page_obj': page_obj,
        'action_choices': AuditLog.ACTION_CHOICES,
        'selected_action': action_filter,
    })


# ── Bookings (all) ─────────────────────────────────────────────────────────────

@require_super_admin
def bookings_list(request):
    qs = Booking.objects.select_related('user', 'room__property').order_by('-check_in')

    # Invalid filter values are ignored (shown as "no filter") rather than 500-ing.
    status_filter = request.GET.get('status', '')
    if status_filter not in dict(Booking.STATUS_CHOICES):
        status_filter = ''
    property_filter = clean_uuid(request.GET.get('property')) or ''
    date_from = clean_date(request.GET.get('from'))
    date_to = clean_date(request.GET.get('to'))
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

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    properties = Property.objects.filter(is_active=True).order_by('name')

    from payments.models import Payment
    all_rooms = Room.objects.filter(is_active=True).select_related('property').order_by('property__name', 'name')

    return render(request, 'superadmin/bookings.html', {
        'bookings': page_obj,
        'page_obj': page_obj,
        'properties': properties,
        'all_rooms': all_rooms,
        'payment_methods': Payment.METHOD_CHOICES,
        'status_choices': Booking.STATUS_CHOICES,
        'status_filter': status_filter,
        'property_filter': property_filter,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to else '',
        'q': q,
    })


@require_super_admin
@require_POST
def walk_in_booking_create(request):
    from rooms.services import create_walk_in_booking
    from payments.models import Payment
    from datetime import datetime
    from decimal import InvalidOperation

    room_id = clean_uuid(request.POST.get('room_id'))
    if room_id is None:
        return JsonResponse({'error': 'Choose a valid room.'}, status=400)
    room = get_object_or_404(Room, pk=room_id)

    try:
        check_in = datetime.strptime(request.POST.get('check_in', ''), '%Y-%m-%d').date()
        check_out = datetime.strptime(request.POST.get('check_out', ''), '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid check-in or check-out date format.'}, status=400)

    guest_name = request.POST.get('guest_name', '').strip()
    guest_phone = request.POST.get('guest_phone', '').strip()
    if not guest_name or not guest_phone:
        return JsonResponse({'error': 'Guest name and phone number are required.'}, status=400)

    try:
        guests = int(request.POST.get('guests', 1))
    except ValueError:
        guests = 1

    payment_method = request.POST.get('payment_method', Payment.METHOD_CASH)
    price_override = None
    override_val = request.POST.get('price_override', '').strip()
    if override_val:
        try:
            price_override = Decimal(override_val)
        except InvalidOperation:
            return JsonResponse({'error': 'Invalid price override.'}, status=400)

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
        _log(request, 'WALK_IN_BOOKING_CREATED', target_user=booking.user,
             detail=f"Walk-in booking: ref={booking.booking_reference}, room={room.name}, method={payment_method}")
        return JsonResponse({
            'message': f'Walk-in booking created successfully. Ref: {booking.booking_reference}',
            'booking_reference': booking.booking_reference,
            'booking_id': str(booking.id),
        })
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.exception("Error creating walk-in booking: %s", e)
        return JsonResponse({'error': 'Internal server error while creating booking.'}, status=500)


@require_super_admin
@require_POST
def booking_cancel(request, booking_id):
    from payments.models import Payment
    booking = get_object_or_404(Booking, pk=booking_id)
    if booking.status not in ('confirmed', 'pending'):
        return JsonResponse({'error': 'Only confirmed or pending bookings can be cancelled.'}, status=400)
    reason = request.POST.get('reason', '').strip() or 'Cancelled by super admin'
    room = booking.room

    paid = booking.payments.filter(status='captured') \
        .aggregate(t=Sum('amount'))['t'] or Decimal('0')

    with transaction.atomic():
        # Only returns a coupon *reserved on a hold* ("applied") to active; a coupon
        # already redeemed on a paid booking is deliberately left redeemed.
        booking.release_coupon()
        booking.status = 'cancelled'
        booking.save(update_fields=['status'])
        # Reopen the nights on OTAs (outbox row commits with the cancellation).
        from core.ota.dispatch import record_ari_change
        record_ari_change(
            room.room_type, room.property_id, booking.check_in, booking.check_out,
            change_types=("availability",),
        )
        detail = f"booking={booking.booking_reference}, reason={reason}"
        if paid > 0:
            detail += f", refund owed: ₹{paid} (manual)"
        _log(request, 'BOOKING_CANCELLED', target_user=booking.user, detail=detail)

    message = 'Booking cancelled.'
    if paid > 0:
        message += f' Refund of ₹{paid} is owed to the guest and must be processed manually.'
    return JsonResponse({'message': message})


@require_super_admin
@require_POST
def booking_complete(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    try:
        booking.complete_stay()
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    _log(request, 'BOOKING_COMPLETED', target_user=booking.user,
         detail=f"booking={booking.booking_reference}, check_out={booking.check_out}")
    return JsonResponse({'message': 'Booking marked as completed.'})

# ── Guests & Loyalty ──────────────────────────────────────────────────────────

@require_super_admin
def guests_list(request):

    q = request.GET.get('q', '').strip()

    guests = User.objects.filter(
        userprofile__role='guest'
    ).select_related('userprofile').annotate(
        stay_count=Count('bookings', filter=Q(bookings__status__in=REVENUE_STATUSES)),
    ).order_by('-date_joined')

    if q:
        guests = guests.filter(
            Q(full_name__icontains=q) | Q(email__icontains=q)
        )

    paginator = Paginator(guests, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    guest_data = []
    for u in page_obj:
        profile = getattr(u, 'userprofile', None)
        guest_data.append({
            'user': u,
            'profile': profile,
            'booking_count': u.stay_count,
        })

    return render(request, 'superadmin/guests.html', {
        'guests': guest_data,
        'page_obj': page_obj,
        'q': q,
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
    try:
        data = parse_json(request)
    except BadInput as e:
        return e.response()
    action = data.get('action')

    if action == 'toggle_active':
        prop.is_active = not prop.is_active
        prop.save(update_fields=['is_active'])
        state = 'activated' if prop.is_active else 'deactivated'
        _log(request, 'PROPERTY_UPDATED', detail=f"property={prop.name}, {state}")
        return JsonResponse({'message': f'Property {state}.', 'is_active': prop.is_active})

    if action == 'update_details':
        try:
            for field in ('name', 'city', 'address', 'whatsapp_number'):
                val = data.get(field)
                if val is not None:
                    setattr(prop, field, _text(val, field, required=field in ('name', 'city')))
        except BadInput as e:
            return e.response()
        prop.save()
        _log(request, 'PROPERTY_UPDATED', detail=f"property={prop.name}")
        return JsonResponse({'message': 'Property updated.'})

    return JsonResponse({'error': UNKNOWN_ACTION_ERR}, status=400)


# ── Room Create ────────────────────────────────────────────────────────────────

@require_super_admin
@require_POST
def room_create(request):
    property_id = request.POST.get('property_id')
    name = request.POST.get('name', '').strip()

    if not property_id or not name:
        return JsonResponse({'error': 'Property and room name are required.'}, status=400)

    try:
        clean_prop_id = clean_uuid(property_id)
        if clean_prop_id is None:
            raise BadInput('Invalid property.')
        fields = {
            'name': _clean_room_field('name', name),
            'room_type': _clean_room_field('room_type', request.POST.get('room_type', 'single')),
            'price_per_night': _clean_room_field('price_per_night', request.POST.get('price_per_night', '0')),
            'capacity': _clean_room_field('capacity', request.POST.get('capacity', '2')),
            'amenities': _clean_room_field('amenities', request.POST.get('amenities', '')),
            'description': _clean_room_field('description', request.POST.get('description', '')),
            'rating': _clean_room_field('rating', request.POST.get('rating', '4.5')),
        }
    except BadInput as e:
        return e.response()

    prop = get_object_or_404(Property, pk=clean_prop_id)
    room = Room.objects.create(property=prop, city=prop.city, **fields)
    _log(request, 'ROOM_CREATED', detail=(
        f"room={room.name}, property={prop.name}, type={room.room_type}, "
        f"price={room.price_per_night}, capacity={room.capacity}"))
    # New inventory: open it on OTAs.
    _push_ari(room.room_type, prop.id, ("availability",))
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
    image_files = request.FILES.getlist('image')
    if not image_files:
        return JsonResponse({'error': 'No image files provided.'}, status=400)

    caption = request.POST.get('caption', '').strip()
    is_primary = request.POST.get('is_primary') == 'on'

    if is_primary:
        room.images.filter(is_primary=True).update(is_primary=False)

    uploaded_ids = []
    for idx, image_file in enumerate(image_files):
        primary = is_primary if idx == 0 else False
        img = RoomImage.objects.create(
            room=room, image=image_file, caption=caption, is_primary=primary,
            order=room.images.count(),
        )
        uploaded_ids.append(str(img.id))
        _log(request, 'ROOM_IMAGE_UPLOADED', detail=f"room={room.name}, image={img.id}")

    return JsonResponse({'message': f'{len(image_files)} image(s) uploaded.'})


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
    _log(request, 'ROOM_IMAGE_PRIMARY_SET', detail=f"room={img.room.name}, image={img.id}")
    return JsonResponse({'message': 'Set as primary image.'})


# ── Room Status Board ──────────────────────────────────────────────────────────

@require_super_admin
def room_status_board(request):
    properties = Property.objects.filter(is_active=True).prefetch_related('rooms')
    return render(request, 'superadmin/room_status_board.html', {
        'properties': properties,
        'status_choices': Room.OPERATIONAL_STATUS_CHOICES,
    })


@require_super_admin
@require_GET
def room_status_board_data(request):
    rooms = Room.objects.select_related('property').order_by('property__name', 'name')
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


# ── Causes ──────────────────────────────────────────────────────────────────

@require_super_admin
def causes_list(request):
    from core.models import Cause
    causes_qs = Cause.objects.all().order_by('sort_order', '-created_at')
    
    paginator = Paginator(causes_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    return render(request, 'superadmin/causes.html', {
        'causes': page_obj,
        'page_obj': page_obj,
    })


@require_super_admin
@require_POST
def cause_create(request):
    from core.models import Cause
    title = request.POST.get('title', '').strip()
    location = request.POST.get('location', '').strip()
    description = request.POST.get('description', '').strip()
    target_amount = request.POST.get('target_amount', '0')
    raised_amount = request.POST.get('raised_amount', '0')
    image_file = request.FILES.get('image')
    whatsapp_link = request.POST.get('whatsapp_link', '').strip()

    if not title or not location:
        return JsonResponse({'error': 'Title and Location are required.'}, status=400)

    try:
        target_amount = to_decimal(target_amount, 'target amount', min_value=0, max_value=MAX_BIG_MONEY)
        raised_amount = to_decimal(raised_amount, 'raised amount', min_value=0, max_value=MAX_BIG_MONEY)
    except BadInput as e:
        return e.response()

    cause = Cause.objects.create(
        title=title, location=location, description=description,
        target_amount=target_amount, raised_amount=raised_amount,
        image=image_file, whatsapp_link=whatsapp_link,
    )
    _log(request, 'CAUSE_CREATED', detail=f"cause={cause.title}")
    return JsonResponse({'message': f'Cause "{cause.title}" created.', 'id': str(cause.id)})


def _cause_toggle_active(request, cause, data):
    cause.is_active = not cause.is_active
    cause.save(update_fields=['is_active'])
    state = 'activated' if cause.is_active else 'deactivated'
    _log(request, 'CAUSE_UPDATED', detail=f"cause={cause.title}, {state}")
    return JsonResponse({'message': f'Cause {state}.', 'is_active': cause.is_active})

def _cause_delete(request, cause, data):
    title = cause.title
    if cause.image:
        cause.image.delete(save=False)
    cause.delete()
    _log(request, 'CAUSE_DELETED', detail=f"cause={title}")
    return JsonResponse({'message': 'Cause deleted.'})

def _cause_update_details(request, cause, data):
    fields_changed = []

    title_val = data.get('title')
    loc_val = data.get('location')
    desc_val = data.get('description')
    target_val = data.get('target_amount')
    raised_val = data.get('raised_amount')
    sort_val = data.get('sort_order')

    if title_val is not None:
        cause.title = _text(title_val, 'title')
        fields_changed.append('title')
    if loc_val is not None:
        cause.location = _text(loc_val, 'location')
        fields_changed.append('location')
    if desc_val is not None:
        cause.description = _text(desc_val, 'description')
        fields_changed.append('description')
    if target_val is not None:
        cause.target_amount = to_decimal(target_val, 'target amount', min_value=0, max_value=MAX_BIG_MONEY)
        fields_changed.append('target_amount')
    if raised_val is not None:
        cause.raised_amount = to_decimal(raised_val, 'raised amount', min_value=0, max_value=MAX_BIG_MONEY)
        fields_changed.append('raised_amount')
    if sort_val is not None:
        cause.sort_order = to_int(sort_val, 'sort order', min_value=0, max_value=MAX_SMALL_INT)
        fields_changed.append('sort_order')

    whatsapp_link_val = data.get('whatsapp_link')
    if whatsapp_link_val is not None:
        cause.whatsapp_link = _text(whatsapp_link_val, 'whatsapp link')
        fields_changed.append('whatsapp_link')

    if request.FILES.get('image'):
        if cause.image:
            cause.image.delete(save=False)
        cause.image = request.FILES['image']
        fields_changed.append('image')

    if fields_changed:
        cause.save()
        _log(request, 'CAUSE_UPDATED', detail=f"cause={cause.title}, fields={fields_changed}")
    return JsonResponse({'message': 'Cause updated.'})

@require_super_admin
@require_POST
def cause_update(request, cause_id):
    from core.models import Cause
    cause = get_object_or_404(Cause, pk=cause_id)
    
    if request.content_type == 'application/json':
        try:
            data = parse_json(request)
        except BadInput as e:
            return e.response()
        action = data.get('action')
    else:
        action = request.POST.get('action')
        data = request.POST

    handlers = {
        'toggle_active': _cause_toggle_active,
        'delete': _cause_delete,
        'update_details': _cause_update_details,
    }
    
    handler = handlers.get(action)
    if handler:
        try:
            return handler(request, cause, data)
        except BadInput as e:
            return e.response()

    return JsonResponse({'error': UNKNOWN_ACTION_ERR}, status=400)


# ── Events / Attractions ─────────────────────────────────────────────────────

@require_super_admin
def events_list(request):
    from core.models import Attraction
    category_filter = request.GET.get('category', '')
    city_filter = request.GET.get('city', '')
    
    events = Attraction.objects.all().order_by('city', 'sort_order', 'name')
    if category_filter:
        events = events.filter(category=category_filter)
    if city_filter:
        events = events.filter(city=city_filter)
        
    paginator = Paginator(events, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'superadmin/events.html', {
        'events': page_obj,
        'page_obj': page_obj,
        'category_choices': Attraction.CATEGORY_CHOICES,
        'category_filter': category_filter,
        'city_filter': city_filter,
    })


@require_super_admin
@require_POST
def event_create(request):
    from core.models import Attraction
    name = request.POST.get('name', '').strip()
    city = request.POST.get('city', '').strip()
    category = request.POST.get('category', 'EVENT').strip()
    description = request.POST.get('description', '').strip()
    address = request.POST.get('address', '').strip()
    opening_hrs = request.POST.get('opening_hrs', '').strip()
    whatsapp_link = request.POST.get('whatsapp_link', '').strip()

    if not name or not city or not category:
        return JsonResponse({'error': 'Name, City, and Category are required.'}, status=400)

    event = Attraction.objects.create(
        name=name, city=city, category=category, description=description,
        address=address, opening_hrs=opening_hrs, whatsapp_link=whatsapp_link,
        created_by=request.user
    )
    _log(request, 'EVENT_CREATED', detail=f"event={event.name}")
    return JsonResponse({'message': f'Event "{event.name}" created.', 'id': str(event.id)})


def _event_toggle_visible(request, event, data):
    event.is_visible = not event.is_visible
    event.save(update_fields=['is_visible'])
    state = 'visible' if event.is_visible else 'hidden'
    _log(request, 'EVENT_UPDATED', detail=f"event={event.name}, {state}")
    return JsonResponse({'message': f'Event is now {state}.', 'is_visible': event.is_visible})

def _event_delete(request, event, data):
    name = event.name
    event.delete()
    _log(request, 'EVENT_DELETED', detail=f"event={name}")
    return JsonResponse({'message': 'Event deleted.'})

def _event_update_details(request, event, data):
    fields_changed = []
    for field in ('name', 'city', 'category', 'description', 'address', 'opening_hrs', 'sort_order', 'whatsapp_link'):
        val = data.get(field)
        if val is not None:
            if field == 'sort_order':
                val = to_int(val, 'sort order', min_value=0, max_value=MAX_SMALL_INT)
            else:
                val = _text(val, field)
            setattr(event, field, val)
            fields_changed.append(field)
    if fields_changed:
        event.save()
        _log(request, 'EVENT_UPDATED', detail=f"event={event.name}, fields={fields_changed}")
    return JsonResponse({'message': 'Event updated.'})

@require_super_admin
@require_POST
def event_update(request, event_id):
    from core.models import Attraction
    event = get_object_or_404(Attraction, pk=event_id)
    try:
        data = parse_json(request)
    except BadInput as e:
        return e.response()
    action = data.get('action')

    handlers = {
        'toggle_visible': _event_toggle_visible,
        'delete': _event_delete,
        'update_details': _event_update_details,
    }
    
    handler = handlers.get(action)
    if handler:
        try:
            return handler(request, event, data)
        except BadInput as e:
            return e.response()

    return JsonResponse({'error': UNKNOWN_ACTION_ERR}, status=400)


@require_super_admin
def event_images(request, event_id):
    from core.models import Attraction
    event = get_object_or_404(Attraction, pk=event_id)
    images = event.photos.all().order_by('sort_order', '-is_primary')
    return render(request, 'superadmin/event_images.html', {
        'event': event,
        'images': images,
    })


@require_super_admin
@require_POST
def event_image_upload(request, event_id):
    from core.models import Attraction, AttractionPhoto
    event = get_object_or_404(Attraction, pk=event_id)
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'error': 'No image file provided.'}, status=400)

    is_primary = request.POST.get('is_primary') == 'on'
    try:
        sort_order = to_int(request.POST.get('sort_order', '0') or 0, 'sort order',
                            min_value=0, max_value=MAX_SMALL_INT)
    except BadInput as e:
        return e.response()

    if is_primary:
        event.photos.filter(is_primary=True).update(is_primary=False)

    img = AttractionPhoto.objects.create(
        attraction=event, image=image_file, is_primary=is_primary,
        sort_order=sort_order or event.photos.count(),
    )
    _log(request, 'EVENT_IMAGE_UPLOADED', detail=f"event={event.name}, image={img.id}")
    return JsonResponse({'message': 'Image uploaded.', 'id': str(img.id)})


@require_super_admin
@require_POST
def event_image_delete(request, image_id):
    from core.models import AttractionPhoto
    img = get_object_or_404(AttractionPhoto, pk=image_id)
    event_name = img.attraction.name
    img.image.delete(save=False)
    img.delete()
    _log(request, 'EVENT_IMAGE_DELETED', detail=f"event={event_name}")
    return JsonResponse({'message': 'Image deleted.'})


@require_super_admin
@require_POST
def event_image_set_primary(request, image_id):
    from core.models import AttractionPhoto
    img = get_object_or_404(AttractionPhoto, pk=image_id)
    img.attraction.photos.filter(is_primary=True).update(is_primary=False)
    img.is_primary = True
    img.save(update_fields=['is_primary'])
    _log(request, 'EVENT_IMAGE_PRIMARY_SET', detail=f"event={img.attraction.name}, image={img.id}")
    return JsonResponse({'message': 'Set as primary image.'})


# ── Activities (Things to Do) ───────────────────────────────────────────────

@require_super_admin
def activities_list(request):
    from core.models import Activity
    activities_qs = Activity.objects.all().order_by('sort_order', '-created_at')
    
    paginator = Paginator(activities_qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    return render(request, 'superadmin/activities.html', {
        'activities': page_obj,
        'page_obj': page_obj,
    })


@require_super_admin
@require_POST
def activity_create(request):
    from core.models import Activity
    title = request.POST.get('title', '').strip()
    category = request.POST.get('category', '').strip()
    description = request.POST.get('description', '').strip()
    price = request.POST.get('price', REQ_TO_BOOK).strip() or REQ_TO_BOOK
    image_file = request.FILES.get('image')
    whatsapp_link = request.POST.get('whatsapp_link', '').strip()
    whatsapp_message = request.POST.get('whatsapp_message', '').strip()

    if not title or not category:
        return JsonResponse({'error': 'Title and Category are required.'}, status=400)

    activity = Activity.objects.create(
        title=title, category=category, description=description,
        price=price, image=image_file, whatsapp_link=whatsapp_link,
        whatsapp_message=whatsapp_message,
    )
    _log(request, 'ACTIVITY_CREATED', detail=f"activity={activity.title}")
    return JsonResponse({'message': f'Activity "{activity.title}" created.', 'id': str(activity.id)})


def _activity_toggle_active(request, activity, data):
    activity.is_active = not activity.is_active
    activity.save(update_fields=['is_active'])
    state = 'activated' if activity.is_active else 'deactivated'
    _log(request, 'ACTIVITY_UPDATED', detail=f"activity={activity.title}, {state}")
    return JsonResponse({'message': f'Activity {state}.', 'is_active': activity.is_active})

def _activity_delete(request, activity, data):
    title = activity.title
    if activity.image:
        activity.image.delete(save=False)
    activity.delete()
    _log(request, 'ACTIVITY_DELETED', detail=f"activity={title}")
    return JsonResponse({'message': 'Activity deleted.'})

def _activity_update_details(request, activity, data):
    fields_changed = []

    title_val = data.get('title')
    cat_val = data.get('category')
    desc_val = data.get('description')
    price_val = data.get('price')
    sort_val = data.get('sort_order')
    whatsapp_link_val = data.get('whatsapp_link')
    whatsapp_message_val = data.get('whatsapp_message')

    if title_val is not None:
        activity.title = _text(title_val, 'title')
        fields_changed.append('title')
    if cat_val is not None:
        activity.category = _text(cat_val, 'category')
        fields_changed.append('category')
    if desc_val is not None:
        activity.description = _text(desc_val, 'description')
        fields_changed.append('description')
    if price_val is not None:
        activity.price = _text(price_val, 'price') or REQ_TO_BOOK
        fields_changed.append('price')
    if sort_val is not None:
        activity.sort_order = to_int(sort_val, 'sort order', min_value=0, max_value=MAX_SMALL_INT)
        fields_changed.append('sort_order')
    if whatsapp_link_val is not None:
        activity.whatsapp_link = _text(whatsapp_link_val, 'whatsapp link')
        fields_changed.append('whatsapp_link')
    if whatsapp_message_val is not None:
        activity.whatsapp_message = _text(whatsapp_message_val, 'whatsapp message')
        fields_changed.append('whatsapp_message')

    if request.FILES.get('image'):
        if activity.image:
            activity.image.delete(save=False)
        activity.image = request.FILES['image']
        fields_changed.append('image')

    if fields_changed:
        activity.save()
        _log(request, 'ACTIVITY_UPDATED', detail=f"activity={activity.title}, fields={fields_changed}")
    return JsonResponse({'message': 'Activity updated.'})

@require_super_admin
@require_POST
def activity_update(request, activity_id):
    from core.models import Activity
    activity = get_object_or_404(Activity, pk=activity_id)

    if request.content_type == 'application/json':
        try:
            data = parse_json(request)
        except BadInput as e:
            return e.response()
        action = data.get('action')
    else:
        action = request.POST.get('action')
        data = request.POST

    handlers = {
        'toggle_active': _activity_toggle_active,
        'delete': _activity_delete,
        'update_details': _activity_update_details,
    }
    
    handler = handlers.get(action)
    if handler:
        try:
            return handler(request, activity, data)
        except BadInput as e:
            return e.response()

    return JsonResponse({'error': UNKNOWN_ACTION_ERR}, status=400)


# ── Site Banners ───────────────────────────────────────────────────────────────

@require_super_admin
def banners_list(request):
    from core.models import SiteBanner
    banners = SiteBanner.objects.all().order_by('target_page', 'sort_order', '-created_at')
    return render(request, 'superadmin/banners.html', {
        'banners': banners,
        'page_choices': SiteBanner.PAGE_CHOICES,
    })


@require_super_admin
@require_POST
def banner_create(request):
    from core.models import SiteBanner
    title = request.POST.get('title', '').strip()
    target_page = request.POST.get('target_page', 'home')
    subtitle = request.POST.get('subtitle', '').strip()
    cta_label = request.POST.get('cta_label', 'Explore Stays').strip()
    cta_url = request.POST.get('cta_url', '/rooms/search/').strip()
    image = request.FILES.get('image')

    if not title or not image:
        messages.error(request, 'Title and hero image are required.')
        return redirect('superadmin:banners-list')
    try:
        sort_order = to_int(request.POST.get('sort_order', 0) or 0, 'sort order',
                            min_value=0, max_value=MAX_SMALL_INT)
    except BadInput as e:
        messages.error(request, f'Banner not created: {e.message}')
        return redirect('superadmin:banners-list')
    if target_page not in dict(SiteBanner.PAGE_CHOICES):
        messages.error(request, 'Banner not created: choose a valid page.')
        return redirect('superadmin:banners-list')

    mobile_image = request.FILES.get('mobile_image')

    banner = SiteBanner.objects.create(
        title=title,
        target_page=target_page,
        subtitle=subtitle,
        cta_label=cta_label,
        cta_url=cta_url,
        sort_order=sort_order,
        image=image,
        mobile_image=mobile_image,
        is_active=True,
    )
    from django.core.cache import cache
    cache.delete('ttr_site_banners_map')

    _log(request, 'BANNER_CREATED', detail=f"banner={banner.title}, page={banner.target_page}")
    messages.success(request, f'Banner "{banner.title}" created successfully.')
    return redirect('superadmin:banners-list')


@require_super_admin
@require_POST
def banner_toggle(request, banner_id):
    from core.models import SiteBanner
    from django.core.cache import cache
    banner = get_object_or_404(SiteBanner, pk=banner_id)
    banner.is_active = not banner.is_active
    banner.save(update_fields=['is_active'])
    cache.delete('ttr_site_banners_map')
    _log(request, 'BANNER_UPDATED', detail=(
        f"banner={banner.title}, {'activated' if banner.is_active else 'deactivated'}"))
    return JsonResponse({'message': 'Status updated.', 'is_active': banner.is_active})


@require_super_admin
@require_POST
def banner_delete(request, banner_id):
    from core.models import SiteBanner
    from django.core.cache import cache
    banner = get_object_or_404(SiteBanner, pk=banner_id)
    title = banner.title
    banner.delete()
    cache.delete('ttr_site_banners_map')
    _log(request, 'BANNER_DELETED', detail=f"banner={title}")
    return JsonResponse({'message': f'Banner "{title}" deleted.'})



