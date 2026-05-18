# Plan B — Superadmin Portal Completions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisite:** Plan A (Security & Bug Fixes) must be merged first. This plan depends on the new audit action codes and the corrected Room status enum.

**Goal:** Make the Super Admin portal the genuine "single pane of glass" — live ops dashboard, full booking control (search/filter/cancel), real analytics, room management across all properties, guest/loyalty oversight, and a property reassignment flow for employees.

**Architecture:** Each feature is a self-contained slice — view + URL + template + audit log + tests. All write actions go through `_log()` so every action is traceable. Server-side role + property checks on every view; client UI is pure render.

**Tech Stack:** Django 6 + Django ORM, server-rendered templates with vanilla JS for AJAX, existing `superadmin/base.html` design system.

---

## Real-world use cases this plan unlocks

| Scenario | Currently | After this plan |
|----------|-----------|-----------------|
| Guest calls to cancel — super admin needs to cancel and refund | No cancel button anywhere | One click cancel in bookings page; audit logged with reason |
| Front-desk reports "room 12 flooded" — super admin needs to mark out-of-order | No room mgmt page in superadmin | Rooms page with operational status dropdown per room |
| Quarterly review — owner asks "revenue by property for Q1" | Analytics hardcoded to current month | Date-range selector with revenue + occupancy + avg stay |
| Guest complains "I didn't get points for my Diwali stay" | No way to view or adjust guest points | Guests page with loyalty ledger; manual adjustment with audit |
| Employee leaves Pondicherry, moves to Bengaluru | Can only assign properties on creation | Property reassignment via update modal |
| Morning check — "how busy are we today?" | Dashboard shows 4 KPIs only | Dashboard shows today's check-ins/outs + pending holds + recent bookings |

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `superadmin/views.py` | Modify | Enhance `dashboard`, `bookings_list`, `analytics`, `employee_update`; add `booking_cancel`, `rooms_list`, `room_status_update`, `guests_list`, `loyalty_adjust` |
| `superadmin/urls.py` | Modify | Add 5 new URL patterns |
| `superadmin/templates/superadmin/dashboard.html` | Modify | Add today's check-ins/outs, pending holds, recent bookings |
| `superadmin/templates/superadmin/bookings.html` | Modify | Filter form + cancel button |
| `superadmin/templates/superadmin/analytics.html` | Modify | Date range + occupancy table |
| `superadmin/templates/superadmin/employees.html` | Modify | Property reassignment modal |
| `superadmin/templates/superadmin/rooms.html` | Create | New rooms management page |
| `superadmin/templates/superadmin/guests.html` | Create | New guest/loyalty management page |
| `superadmin/templates/superadmin/base.html` | Modify | Add "Rooms" and "Guests" links to sidebar |
| `superadmin/tests.py` | Create | Tests per task |

---

## Task 1: Enhanced Dashboard

**Files:**
- Modify: `superadmin/views.py` — `dashboard()` (around line 32)
- Modify: `superadmin/templates/superadmin/dashboard.html`
- Create: `superadmin/tests.py`

- [ ] **Step 1: Replace `dashboard()` body in `superadmin/views.py`**

```python
@require_super_admin
def dashboard(request):
    today = timezone.now().date()
    month_start = today.replace(day=1)
    now = timezone.now()

    confirmed = Booking.objects.filter(status='confirmed')

    active_bookings = confirmed.filter(check_in__lte=today, check_out__gt=today).count()
    todays_checkins = confirmed.filter(check_in=today).count()
    todays_checkouts = confirmed.filter(check_out=today).count()

    pending_holds = Booking.objects.filter(
        status='pending', hold_expires_at__gt=now,
    ).count()

    today_revenue = confirmed.filter(check_in=today).aggregate(
        t=Sum('total_price'))['t'] or 0
    month_revenue = confirmed.filter(check_in__gte=month_start).aggregate(
        t=Sum('total_price'))['t'] or 0

    total_rooms = Room.objects.count()
    total_guests = User.objects.filter(userprofile__role='guest').count()

    recent_bookings = Booking.objects.select_related(
        'user', 'room', 'room__property'
    ).order_by('-created_at')[:8]

    return render(request, 'superadmin/dashboard.html', {
        'active_bookings': active_bookings,
        'todays_checkins': todays_checkins,
        'todays_checkouts': todays_checkouts,
        'pending_holds': pending_holds,
        'today_revenue': today_revenue,
        'month_revenue': month_revenue,
        'total_rooms': total_rooms,
        'total_guests': total_guests,
        'recent_bookings': recent_bookings,
    })
```

- [ ] **Step 2: Replace the template at `superadmin/templates/superadmin/dashboard.html`**

```html
{% extends "superadmin/base.html" %}
{% block title %}Dashboard{% endblock %}
{% block page_title %}Dashboard{% endblock %}
{% block content %}

<div class="grid-4" style="margin-bottom:20px;">
  <div class="card"><div class="card-title">Active Bookings</div><div class="card-value">{{ active_bookings }}</div></div>
  <div class="card"><div class="card-title">Check-ins Today</div><div class="card-value">{{ todays_checkins }}</div></div>
  <div class="card"><div class="card-title">Check-outs Today</div><div class="card-value">{{ todays_checkouts }}</div></div>
  <div class="card"><div class="card-title">Pending Holds</div><div class="card-value">{{ pending_holds }}</div></div>
</div>

<div class="grid-4" style="margin-bottom:24px;">
  <div class="card"><div class="card-title">Today's Revenue</div><div class="card-value">₹{{ today_revenue|floatformat:0 }}</div></div>
  <div class="card"><div class="card-title">Month Revenue</div><div class="card-value">₹{{ month_revenue|floatformat:0 }}</div></div>
  <div class="card"><div class="card-title">Total Rooms</div><div class="card-value">{{ total_rooms }}</div></div>
  <div class="card"><div class="card-title">Total Guests</div><div class="card-value">{{ total_guests }}</div></div>
</div>

<div class="card">
  <div class="section-head">
    <h2>Recent Bookings</h2>
    <a href="{% url 'superadmin:bookings' %}" class="btn btn-ghost btn-sm">View All</a>
  </div>
  <table class="sa-table">
    <thead><tr><th>Ref</th><th>Guest</th><th>Room / Property</th><th>Check-in</th><th>Total</th><th>Status</th></tr></thead>
    <tbody>
      {% for b in recent_bookings %}
      <tr>
        <td style="font-size:.8rem;font-family:monospace;">{{ b.booking_reference|default:b.id|truncatechars:14 }}</td>
        <td>{{ b.user.email }}</td>
        <td>{{ b.room.name }}<br><small style="color:var(--muted);">{{ b.room.property.name|default:"—" }}</small></td>
        <td>{{ b.check_in }}</td>
        <td>₹{{ b.total_price|floatformat:0 }}</td>
        <td>
          {% if b.status == 'confirmed' %}<span class="badge badge-success">Confirmed</span>
          {% elif b.status == 'completed' %}<span class="badge badge-accent">Completed</span>
          {% elif b.status == 'cancelled' %}<span class="badge badge-danger">Cancelled</span>
          {% elif b.status == 'pending' %}<span class="badge badge-muted">Pending</span>
          {% else %}<span class="badge badge-muted">{{ b.status }}</span>{% endif %}
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="6" style="text-align:center;color:var(--muted);padding:20px;">No bookings yet.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% endblock %}
```

- [ ] **Step 3: Write a context-level test**

Create `superadmin/tests.py`:

```python
import datetime
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from rooms.models import Property, Room, Booking

User = get_user_model()


def _make_super_admin(email='sa@x.com'):
    u = User.objects.create_user(email=email, password='pass1234', is_active=True)
    u.userprofile.role = 'super_admin'
    u.userprofile.save()
    return u


class DashboardContextTest(TestCase):
    def setUp(self):
        self.sa = _make_super_admin()
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.room = Room.objects.create(property=self.prop, name='R', city='Pondy',
                                        room_type='single', price_per_night=2000, capacity=2)
        self.guest = User.objects.create_user(email='g@x.com', password='x', is_active=True)
        today = timezone.now().date()
        # one confirmed checking in today
        Booking.objects.create(room=self.room, user=self.guest, check_in=today,
                               check_out=today + datetime.timedelta(days=1),
                               guests=1, status='confirmed', total_price=Decimal('2000'))
        # one pending hold that's still live
        Booking.objects.create(room=self.room, user=self.guest, check_in=today,
                               check_out=today + datetime.timedelta(days=1),
                               guests=1, status='pending', total_price=Decimal('2000'),
                               hold_expires_at=timezone.now() + datetime.timedelta(minutes=5))

    def test_dashboard_renders_with_full_context(self):
        self.client.force_login(self.sa)
        res = self.client.get(reverse('superadmin:dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['todays_checkins'], 1)
        self.assertEqual(res.context['todays_checkouts'], 0)
        self.assertEqual(res.context['pending_holds'], 1)
        self.assertEqual(res.context['recent_bookings'].count(), 2)
```

- [ ] **Step 4: Run the test**

```bash
python manage.py test superadmin.tests.DashboardContextTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add superadmin/views.py superadmin/templates/superadmin/dashboard.html superadmin/tests.py
git commit -m "feat(superadmin): dashboard shows today's check-ins/outs, pending holds, recent bookings"
```

---

## Task 2: Bookings management — filter + cancel action

**Files:**
- Modify: `superadmin/views.py` — `bookings_list()`; add `booking_cancel()`
- Modify: `superadmin/urls.py` — add cancel URL
- Modify: `superadmin/templates/superadmin/bookings.html`
- Append: `superadmin/tests.py`

- [ ] **Step 1: Replace `bookings_list()` in `superadmin/views.py`**

```python
@require_super_admin
def bookings_list(request):
    qs = Booking.objects.select_related('user', 'room', 'room__property').order_by('-check_in')

    status = request.GET.get('status', '').strip()
    property_id = request.GET.get('property', '').strip()
    from_date = request.GET.get('from', '').strip()
    to_date = request.GET.get('to', '').strip()
    q = request.GET.get('q', '').strip()

    if status:
        qs = qs.filter(status=status)
    if property_id:
        qs = qs.filter(room__property_id=property_id)
    if from_date:
        qs = qs.filter(check_in__gte=from_date)
    if to_date:
        qs = qs.filter(check_in__lte=to_date)
    if q:
        qs = qs.filter(
            Q(booking_reference__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__full_name__icontains=q)
        )

    return render(request, 'superadmin/bookings.html', {
        'bookings': qs[:200],
        'properties': Property.objects.filter(is_active=True),
        'status_choices': [
            ('', 'All Statuses'),
            ('confirmed', 'Confirmed'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
            ('pending', 'Pending'),
            ('expired', 'Expired'),
        ],
        'selected': {'status': status, 'property': property_id, 'from': from_date, 'to': to_date, 'q': q},
    })
```

- [ ] **Step 2: Append `booking_cancel()` after `bookings_list()`**

```python
@require_super_admin
@require_POST
def booking_cancel(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    if booking.status not in ('confirmed', 'pending'):
        return JsonResponse(
            {'error': f'Cannot cancel a booking that is {booking.status}.'}, status=400)

    reason = (request.POST.get('reason') or json.loads(request.body or '{}').get('reason') or '').strip()
    previous_status = booking.status
    booking.status = 'cancelled'
    booking.save(update_fields=['status'])

    _log(
        request,
        'BOOKING_CANCELLED',
        target_user=booking.user,
        detail=f"ref={booking.booking_reference} prev={previous_status} reason={reason or '—'}",
    )

    return JsonResponse({'message': f'Booking {booking.booking_reference} cancelled.'})
```

- [ ] **Step 3: Add the URL in `superadmin/urls.py`**

After the existing `bookings/` line, add:

```python
path('bookings/<uuid:booking_id>/cancel/', views.booking_cancel, name='booking-cancel'),
```

- [ ] **Step 4: Replace `superadmin/templates/superadmin/bookings.html`**

```html
{% extends "superadmin/base.html" %}
{% block title %}Bookings{% endblock %}
{% block page_title %}Bookings{% endblock %}
{% block content %}

<form method="get" class="card" style="margin-bottom:16px;">
  <div style="display:grid;grid-template-columns:1.5fr 1.5fr 1fr 1fr 1fr auto;gap:10px;align-items:end;">
    <div class="form-group" style="margin:0;">
      <label>Search (ref / guest)</label>
      <input type="text" name="q" class="form-control" value="{{ selected.q }}" placeholder="TT-2026-... or email">
    </div>
    <div class="form-group" style="margin:0;">
      <label>Property</label>
      <select name="property" class="form-control">
        <option value="">All Properties</option>
        {% for p in properties %}
        <option value="{{ p.pk }}" {% if selected.property == p.pk|stringformat:"s" %}selected{% endif %}>{{ p.name }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group" style="margin:0;">
      <label>Status</label>
      <select name="status" class="form-control">
        {% for val, label in status_choices %}
        <option value="{{ val }}" {% if selected.status == val %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group" style="margin:0;">
      <label>From</label>
      <input type="date" name="from" class="form-control" value="{{ selected.from }}">
    </div>
    <div class="form-group" style="margin:0;">
      <label>To</label>
      <input type="date" name="to" class="form-control" value="{{ selected.to }}">
    </div>
    <button type="submit" class="btn btn-primary">Apply</button>
  </div>
</form>

<div class="card">
  <table class="sa-table">
    <thead><tr><th>Reference</th><th>Guest</th><th>Room / Property</th><th>Check-in</th><th>Check-out</th><th>Total</th><th>Status</th><th></th></tr></thead>
    <tbody>
      {% for b in bookings %}
      <tr>
        <td style="font-size:.8rem;font-family:monospace;">{{ b.booking_reference }}</td>
        <td>{{ b.user.email }}</td>
        <td>{{ b.room.name }}<br><small style="color:var(--muted);">{{ b.room.property.name|default:"—" }}</small></td>
        <td>{{ b.check_in }}</td>
        <td>{{ b.check_out }}</td>
        <td>₹{{ b.total_price|floatformat:0 }}</td>
        <td>
          {% if b.status == 'confirmed' %}<span class="badge badge-success">Confirmed</span>
          {% elif b.status == 'completed' %}<span class="badge badge-accent">Completed</span>
          {% elif b.status == 'cancelled' %}<span class="badge badge-danger">Cancelled</span>
          {% elif b.status == 'pending' %}<span class="badge badge-muted">Pending</span>
          {% elif b.status == 'expired' %}<span class="badge badge-danger">Expired</span>
          {% else %}<span class="badge badge-muted">{{ b.status }}</span>{% endif %}
        </td>
        <td>
          {% if b.status == 'confirmed' or b.status == 'pending' %}
          <button class="btn btn-danger btn-sm" onclick="cancelBooking('{{ b.pk }}', '{{ b.booking_reference }}')">Cancel</button>
          {% endif %}
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px;">No bookings match these filters.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<script>
const CSRF = '{{ csrf_token }}';
function cancelBooking(id, ref) {
  const reason = prompt(`Cancel booking ${ref}? Enter a reason for the audit log:`);
  if (reason === null) return;
  fetch(`/super-admin/bookings/${id}/cancel/`, {
    method: 'POST',
    headers: {'Content-Type':'application/json','X-CSRFToken': CSRF},
    body: JSON.stringify({reason}),
  }).then(r=>r.json()).then(d=>{
    alert(d.message || d.error);
    if (!d.error) location.reload();
  });
}
</script>
{% endblock %}
```

- [ ] **Step 5: Append cancel-flow test in `superadmin/tests.py`**

```python
class BookingCancelTest(TestCase):
    def setUp(self):
        self.sa = _make_super_admin('sa2@x.com')
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.room = Room.objects.create(property=self.prop, name='R', city='Pondy',
                                        room_type='single', price_per_night=2000, capacity=2)
        self.guest = User.objects.create_user(email='g2@x.com', password='x', is_active=True)
        today = timezone.now().date()
        self.booking = Booking.objects.create(
            room=self.room, user=self.guest, check_in=today,
            check_out=today + datetime.timedelta(days=1),
            guests=1, status='confirmed', total_price=Decimal('2000'),
        )

    def test_cancel_confirmed_booking_succeeds_and_logs(self):
        from superadmin.models import AuditLog
        self.client.force_login(self.sa)
        url = reverse('superadmin:booking-cancel', args=[self.booking.pk])
        res = self.client.post(url, data='{"reason":"guest illness"}',
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'cancelled')
        log = AuditLog.objects.filter(action='BOOKING_CANCELLED').first()
        self.assertIsNotNone(log)
        self.assertIn('guest illness', log.detail)

    def test_cannot_cancel_completed_booking(self):
        self.booking.status = 'completed'
        self.booking.save()
        self.client.force_login(self.sa)
        url = reverse('superadmin:booking-cancel', args=[self.booking.pk])
        res = self.client.post(url, data='{"reason":"x"}', content_type='application/json')
        self.assertEqual(res.status_code, 400)
```

- [ ] **Step 6: Run the new tests**

```bash
python manage.py test superadmin.tests.BookingCancelTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add superadmin/views.py superadmin/urls.py superadmin/templates/superadmin/bookings.html superadmin/tests.py
git commit -m "feat(superadmin): bookings page with filters and audited cancel action"
```

---

## Task 3: Analytics — date range + occupancy

**Files:**
- Modify: `superadmin/views.py` — `analytics()`
- Modify: `superadmin/templates/superadmin/analytics.html`
- Append: `superadmin/tests.py`

- [ ] **Step 1: Replace `analytics()` in `superadmin/views.py`**

```python
@require_super_admin
def analytics(request):
    today = timezone.now().date()
    default_from = today.replace(day=1)

    from_str = request.GET.get('from') or default_from.isoformat()
    to_str = request.GET.get('to') or today.isoformat()
    try:
        from_date = timezone.datetime.strptime(from_str, '%Y-%m-%d').date()
        to_date = timezone.datetime.strptime(to_str, '%Y-%m-%d').date()
    except ValueError:
        from_date, to_date = default_from, today

    span_nights = max((to_date - from_date).days, 1)

    confirmed = Booking.objects.filter(
        status__in=('confirmed', 'completed'),
        check_in__gte=from_date,
        check_in__lte=to_date,
    )

    revenue_by_property = (
        confirmed.values('room__property__id', 'room__property__name')
        .annotate(revenue=Sum('total_price'), count=Count('id'))
        .order_by('-revenue')
    )

    occupancy_rows = []
    for p in Property.objects.filter(is_active=True):
        room_count = Room.objects.filter(property=p, is_active=True).count()
        nights_booked = confirmed.filter(room__property=p).count()
        capacity = room_count * span_nights
        rate = (nights_booked / capacity * 100) if capacity else 0
        occupancy_rows.append({
            'property': p.name,
            'rooms': room_count,
            'nights_booked': nights_booked,
            'capacity': capacity,
            'rate': round(rate, 1),
        })

    total_revenue = confirmed.aggregate(t=Sum('total_price'))['t'] or 0
    total_bookings = confirmed.count()
    avg_booking_value = (total_revenue / total_bookings) if total_bookings else 0

    recent_bookings = Booking.objects.filter(status='confirmed').select_related(
        'user', 'room__property').order_by('-check_in')[:20]

    return render(request, 'superadmin/analytics.html', {
        'from_date': from_date,
        'to_date': to_date,
        'span_nights': span_nights,
        'revenue_by_property': revenue_by_property,
        'occupancy_rows': occupancy_rows,
        'total_revenue': total_revenue,
        'total_bookings': total_bookings,
        'avg_booking_value': avg_booking_value,
        'recent_bookings': recent_bookings,
    })
```

- [ ] **Step 2: Replace `superadmin/templates/superadmin/analytics.html`**

```html
{% extends "superadmin/base.html" %}
{% block title %}Analytics{% endblock %}
{% block page_title %}Analytics{% endblock %}
{% block content %}

<form method="get" class="card" style="margin-bottom:16px;">
  <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:12px;align-items:end;">
    <div class="form-group" style="margin:0;"><label>From</label><input type="date" name="from" class="form-control" value="{{ from_date|date:'Y-m-d' }}"></div>
    <div class="form-group" style="margin:0;"><label>To</label><input type="date" name="to" class="form-control" value="{{ to_date|date:'Y-m-d' }}"></div>
    <button type="submit" class="btn btn-primary">Apply</button>
  </div>
</form>

<div class="grid-4" style="margin-bottom:24px;">
  <div class="card"><div class="card-title">Total Revenue</div><div class="card-value">₹{{ total_revenue|floatformat:0 }}</div></div>
  <div class="card"><div class="card-title">Bookings</div><div class="card-value">{{ total_bookings }}</div></div>
  <div class="card"><div class="card-title">Avg Booking Value</div><div class="card-value">₹{{ avg_booking_value|floatformat:0 }}</div></div>
  <div class="card"><div class="card-title">Span (nights)</div><div class="card-value">{{ span_nights }}</div></div>
</div>

<div class="grid-2" style="margin-bottom:24px;">
  <div class="card">
    <div class="section-head"><h2>Revenue by Property</h2></div>
    <table class="sa-table">
      <thead><tr><th>Property</th><th>Bookings</th><th>Revenue</th></tr></thead>
      <tbody>
        {% for row in revenue_by_property %}
        <tr><td>{{ row.room__property__name|default:"—" }}</td><td>{{ row.count }}</td><td>₹{{ row.revenue|floatformat:0 }}</td></tr>
        {% empty %}
        <tr><td colspan="3" style="text-align:center;color:var(--muted);padding:16px;">No data</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="card">
    <div class="section-head"><h2>Occupancy</h2></div>
    <table class="sa-table">
      <thead><tr><th>Property</th><th>Rooms</th><th>Nights Booked</th><th>Capacity</th><th>Rate</th></tr></thead>
      <tbody>
        {% for row in occupancy_rows %}
        <tr>
          <td>{{ row.property }}</td>
          <td>{{ row.rooms }}</td>
          <td>{{ row.nights_booked }}</td>
          <td>{{ row.capacity }}</td>
          <td>
            {% if row.rate >= 70 %}<span class="badge badge-success">{{ row.rate }}%</span>
            {% elif row.rate >= 40 %}<span class="badge badge-accent">{{ row.rate }}%</span>
            {% else %}<span class="badge badge-muted">{{ row.rate }}%</span>{% endif %}
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="5" style="text-align:center;color:var(--muted);padding:16px;">No active properties</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

<div class="card">
  <div class="section-head"><h2>Recent Confirmed Bookings</h2></div>
  <table class="sa-table">
    <thead><tr><th>Ref</th><th>Guest</th><th>Room / Property</th><th>Check-in</th><th>Check-out</th><th>Total</th></tr></thead>
    <tbody>
      {% for b in recent_bookings %}
      <tr>
        <td style="font-size:.8rem;font-family:monospace;">{{ b.booking_reference }}</td>
        <td>{{ b.user.email }}</td>
        <td>{{ b.room.name }}<br><small style="color:var(--muted);">{{ b.room.property.name|default:"—" }}</small></td>
        <td>{{ b.check_in }}</td>
        <td>{{ b.check_out }}</td>
        <td>₹{{ b.total_price|floatformat:0 }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="6" style="text-align:center;color:var(--muted);padding:16px;">No bookings</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

{% endblock %}
```

- [ ] **Step 3: Append analytics test in `superadmin/tests.py`**

```python
class AnalyticsRangeTest(TestCase):
    def setUp(self):
        self.sa = _make_super_admin('sa3@x.com')
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.room = Room.objects.create(property=self.prop, name='R', city='Pondy',
                                        room_type='single', price_per_night=2000, capacity=2,
                                        is_active=True)
        self.guest = User.objects.create_user(email='g3@x.com', password='x', is_active=True)

    def test_analytics_respects_date_range(self):
        Booking.objects.create(room=self.room, user=self.guest,
                               check_in='2026-01-15', check_out='2026-01-17',
                               guests=1, status='confirmed', total_price=Decimal('4000'))
        Booking.objects.create(room=self.room, user=self.guest,
                               check_in='2026-03-10', check_out='2026-03-12',
                               guests=1, status='confirmed', total_price=Decimal('5000'))
        self.client.force_login(self.sa)
        url = reverse('superadmin:analytics') + '?from=2026-01-01&to=2026-01-31'
        res = self.client.get(url)
        self.assertEqual(res.context['total_bookings'], 1)
        self.assertEqual(res.context['total_revenue'], Decimal('4000'))

    def test_occupancy_includes_all_active_properties(self):
        self.client.force_login(self.sa)
        res = self.client.get(reverse('superadmin:analytics'))
        property_names = [r['property'] for r in res.context['occupancy_rows']]
        self.assertIn('P', property_names)
```

- [ ] **Step 4: Run the tests**

```bash
python manage.py test superadmin.tests.AnalyticsRangeTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add superadmin/views.py superadmin/templates/superadmin/analytics.html superadmin/tests.py
git commit -m "feat(superadmin): analytics with date range, occupancy, and KPI cards"
```

---

## Task 4: Rooms management page

**Files:**
- Modify: `superadmin/views.py` — add `rooms_list()` and `room_status_update()`
- Modify: `superadmin/urls.py` — add two URLs
- Modify: `superadmin/templates/superadmin/base.html` — add sidebar link
- Create: `superadmin/templates/superadmin/rooms.html`
- Append: `superadmin/tests.py`

- [ ] **Step 1: Append two views in `superadmin/views.py`**

```python
# ── Rooms (super admin) ────────────────────────────────────────────────────────

@require_super_admin
def rooms_list(request):
    qs = Room.objects.select_related('property').order_by('property__name', 'name')
    property_id = request.GET.get('property', '').strip()
    op_status = request.GET.get('status', '').strip()
    if property_id:
        qs = qs.filter(property_id=property_id)
    if op_status:
        qs = qs.filter(operational_status=op_status)
    return render(request, 'superadmin/rooms.html', {
        'rooms': qs,
        'properties': Property.objects.filter(is_active=True),
        'status_choices': Room.OPERATIONAL_STATUS_CHOICES,
        'selected': {'property': property_id, 'status': op_status},
    })


@require_super_admin
@require_POST
def room_status_update(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    new_status = json.loads(request.body or '{}').get('operational_status')
    valid = {choice[0] for choice in Room.OPERATIONAL_STATUS_CHOICES}
    if new_status not in valid:
        return JsonResponse({'error': 'Invalid status.'}, status=400)
    previous = room.operational_status
    room.operational_status = new_status
    room.save(update_fields=['operational_status'])
    _log(request, 'ROOM_STATUS_UPDATED',
         detail=f"room={room.name} property={room.property.name} {previous}→{new_status}")
    return JsonResponse({'message': 'Status updated.', 'status': new_status})
```

- [ ] **Step 2: Add two URLs in `superadmin/urls.py`**

```python
path('rooms/', views.rooms_list, name='rooms'),
path('rooms/<uuid:room_id>/status/', views.room_status_update, name='room-status-update'),
```

- [ ] **Step 3: Add sidebar link in `superadmin/templates/superadmin/base.html`**

Find the `<nav class="sa-nav">` block. After the `Bookings` link, add:

```html
    <a href="{% url 'superadmin:rooms' %}" class="{% if request.resolver_match.url_name == 'rooms' %}active{% endif %}">
      <span class="icon">🛏</span> Rooms
    </a>
```

- [ ] **Step 4: Create `superadmin/templates/superadmin/rooms.html`**

```html
{% extends "superadmin/base.html" %}
{% block title %}Rooms{% endblock %}
{% block page_title %}Rooms{% endblock %}
{% block content %}

<form method="get" class="card" style="margin-bottom:16px;">
  <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:12px;align-items:end;">
    <div class="form-group" style="margin:0;">
      <label>Property</label>
      <select name="property" class="form-control">
        <option value="">All Properties</option>
        {% for p in properties %}
        <option value="{{ p.pk }}" {% if selected.property == p.pk|stringformat:"s" %}selected{% endif %}>{{ p.name }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="form-group" style="margin:0;">
      <label>Operational Status</label>
      <select name="status" class="form-control">
        <option value="">All Statuses</option>
        {% for val, label in status_choices %}
        <option value="{{ val }}" {% if selected.status == val %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
    </div>
    <button type="submit" class="btn btn-primary">Filter</button>
  </div>
</form>

<div class="card">
  <table class="sa-table">
    <thead><tr><th>Room</th><th>Property</th><th>Type</th><th>Rate</th><th>Active</th><th>Operational Status</th></tr></thead>
    <tbody>
      {% for r in rooms %}
      <tr>
        <td>{{ r.name }}</td>
        <td>{{ r.property.name }} <small style="color:var(--muted);">/ {{ r.city }}</small></td>
        <td><span class="badge badge-muted">{{ r.get_room_type_display }}</span></td>
        <td>₹{{ r.price_per_night|floatformat:0 }}</td>
        <td>{% if r.is_active %}<span class="badge badge-success">Yes</span>{% else %}<span class="badge badge-muted">No</span>{% endif %}</td>
        <td>
          <select class="form-control" style="width:160px;" onchange="updateStatus('{{ r.pk }}', this.value, this)">
            {% for val, label in status_choices %}
            <option value="{{ val }}" {% if r.operational_status == val %}selected{% endif %}>{{ label }}</option>
            {% endfor %}
          </select>
        </td>
      </tr>
      {% empty %}
      <tr><td colspan="6" style="text-align:center;color:var(--muted);padding:20px;">No rooms match.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<script>
const CSRF = '{{ csrf_token }}';
function updateStatus(roomId, value, selectEl) {
  const original = selectEl.dataset.original || selectEl.value;
  fetch(`/super-admin/rooms/${roomId}/status/`, {
    method: 'POST',
    headers: {'Content-Type':'application/json','X-CSRFToken': CSRF},
    body: JSON.stringify({operational_status: value}),
  }).then(r=>r.json()).then(d=>{
    if (d.error) { alert(d.error); selectEl.value = original; }
    else selectEl.dataset.original = value;
  });
}
document.querySelectorAll('select[onchange*="updateStatus"]').forEach(s => s.dataset.original = s.value);
</script>
{% endblock %}
```

- [ ] **Step 5: Append room-status test**

```python
class RoomStatusUpdateTest(TestCase):
    def setUp(self):
        self.sa = _make_super_admin('sa4@x.com')
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.room = Room.objects.create(property=self.prop, name='R', city='Pondy',
                                        room_type='single', price_per_night=2000, capacity=2)

    def test_status_update_succeeds_and_logs(self):
        from superadmin.models import AuditLog
        self.client.force_login(self.sa)
        url = reverse('superadmin:room-status-update', args=[self.room.pk])
        res = self.client.post(url, data='{"operational_status":"maintenance"}',
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.room.refresh_from_db()
        self.assertEqual(self.room.operational_status, 'maintenance')
        self.assertTrue(AuditLog.objects.filter(action='ROOM_STATUS_UPDATED').exists())

    def test_status_update_rejects_unknown_value(self):
        self.client.force_login(self.sa)
        url = reverse('superadmin:room-status-update', args=[self.room.pk])
        res = self.client.post(url, data='{"operational_status":"haunted"}',
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)
```

- [ ] **Step 6: Run the tests**

```bash
python manage.py test superadmin.tests.RoomStatusUpdateTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add superadmin/views.py superadmin/urls.py superadmin/templates/superadmin/ superadmin/tests.py
git commit -m "feat(superadmin): rooms management page with audited status updates"
```

---

## Task 5: Guests + loyalty management page

**Files:**
- Modify: `superadmin/views.py` — add `guests_list()` and `loyalty_adjust()`
- Modify: `superadmin/urls.py` — add two URLs
- Modify: `superadmin/templates/superadmin/base.html` — add sidebar link
- Create: `superadmin/templates/superadmin/guests.html`
- Append: `superadmin/tests.py`

- [ ] **Step 1: Append views in `superadmin/views.py`**

```python
# ── Guests + Loyalty ───────────────────────────────────────────────────────────

@require_super_admin
def guests_list(request):
    from loyalty.models import LoyaltyLedger

    q = request.GET.get('q', '').strip()
    guests = User.objects.filter(userprofile__role='guest').select_related('userprofile')
    if q:
        guests = guests.filter(Q(email__icontains=q) | Q(full_name__icontains=q))
    guests = guests.annotate(booking_count=Count('booking')).order_by('-userprofile__loyalty_points')[:200]

    recent_ledger = LoyaltyLedger.objects.select_related('user', 'booking').order_by('-created_at')[:30]

    return render(request, 'superadmin/guests.html', {
        'guests': guests,
        'recent_ledger': recent_ledger,
        'q': q,
    })


@require_super_admin
@require_POST
def loyalty_adjust(request, user_id):
    from loyalty.models import LoyaltyLedger

    target = get_object_or_404(User, pk=user_id, userprofile__role='guest')
    payload = json.loads(request.body or '{}')
    try:
        delta = int(payload.get('delta', 0))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid delta.'}, status=400)
    if delta == 0:
        return JsonResponse({'error': 'Delta must be non-zero.'}, status=400)

    note = (payload.get('note') or '').strip()
    if not note:
        return JsonResponse({'error': 'A note is required for audit.'}, status=400)

    profile = target.userprofile
    new_points = max(profile.loyalty_points + delta, 0)
    profile.loyalty_points = new_points
    profile.save(update_fields=['loyalty_points'])
    profile.recalculate_tier()

    LoyaltyLedger.objects.create(
        user=target, delta=delta, reason='ADMIN_ADJUSTMENT', note=note,
    )
    _log(request, 'LOYALTY_POINTS_ADJUSTED', target_user=target,
         detail=f"delta={delta} new_total={new_points} note={note}")

    return JsonResponse({
        'message': f'Adjusted by {delta}. New balance: {new_points}.',
        'new_total': new_points,
        'tier': profile.loyalty_tier,
    })
```

- [ ] **Step 2: Add URLs in `superadmin/urls.py`**

```python
path('guests/', views.guests_list, name='guests'),
path('guests/<uuid:user_id>/adjust-loyalty/', views.loyalty_adjust, name='loyalty-adjust'),
```

- [ ] **Step 3: Add sidebar link in `superadmin/templates/superadmin/base.html`**

After the Employees link (or after Rooms link from Task 4), add:

```html
    <a href="{% url 'superadmin:guests' %}" class="{% if request.resolver_match.url_name == 'guests' %}active{% endif %}">
      <span class="icon">👤</span> Guests
    </a>
```

- [ ] **Step 4: Create `superadmin/templates/superadmin/guests.html`**

```html
{% extends "superadmin/base.html" %}
{% block title %}Guests{% endblock %}
{% block page_title %}Guests &amp; Loyalty{% endblock %}
{% block content %}

<form method="get" class="card" style="margin-bottom:16px;">
  <div style="display:grid;grid-template-columns:1fr auto;gap:10px;align-items:end;">
    <div class="form-group" style="margin:0;">
      <label>Search by name or email</label>
      <input type="text" name="q" class="form-control" value="{{ q }}" placeholder="guest@example.com">
    </div>
    <button type="submit" class="btn btn-primary">Search</button>
  </div>
</form>

<div class="card" style="margin-bottom:24px;">
  <div class="section-head"><h2>Guests (top 200 by points)</h2></div>
  <table class="sa-table">
    <thead><tr><th>Guest</th><th>Tier</th><th>Points</th><th>Bookings</th><th>Joined</th><th>Actions</th></tr></thead>
    <tbody>
      {% for g in guests %}
      <tr>
        <td>{{ g.full_name|default:"—" }}<br><small style="color:var(--muted);">{{ g.email }}</small></td>
        <td>
          {% if g.userprofile.loyalty_tier == 'gold' %}<span class="badge badge-accent">Gold</span>
          {% elif g.userprofile.loyalty_tier == 'silver' %}<span class="badge badge-muted">Silver</span>
          {% else %}<span class="badge badge-muted">{{ g.userprofile.loyalty_tier|capfirst }}</span>{% endif %}
        </td>
        <td><strong>{{ g.userprofile.loyalty_points }}</strong></td>
        <td>{{ g.booking_count }}</td>
        <td style="font-size:.8rem;color:var(--muted);">{{ g.date_joined|date:"d M Y" }}</td>
        <td><button class="btn btn-ghost btn-sm" onclick="openAdjust('{{ g.pk }}', '{{ g.email }}', {{ g.userprofile.loyalty_points }})">Adjust Points</button></td>
      </tr>
      {% empty %}
      <tr><td colspan="6" style="text-align:center;color:var(--muted);padding:20px;">No guests match.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="card">
  <div class="section-head"><h2>Recent Loyalty Ledger</h2></div>
  <table class="sa-table">
    <thead><tr><th>When</th><th>Guest</th><th>Δ</th><th>Reason</th><th>Note</th></tr></thead>
    <tbody>
      {% for e in recent_ledger %}
      <tr>
        <td style="font-size:.8rem;white-space:nowrap;">{{ e.created_at|date:"d M Y H:i" }}</td>
        <td>{{ e.user.email }}</td>
        <td>{% if e.delta >= 0 %}<span class="badge badge-success">+{{ e.delta }}</span>{% else %}<span class="badge badge-danger">{{ e.delta }}</span>{% endif %}</td>
        <td><span class="badge badge-muted">{{ e.reason }}</span></td>
        <td style="font-size:.8rem;color:var(--muted);">{{ e.note|default:"—" }}</td>
      </tr>
      {% empty %}
      <tr><td colspan="5" style="text-align:center;color:var(--muted);padding:20px;">No ledger entries.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="modal-overlay" id="adjustModal">
  <div class="modal">
    <div class="modal-title">Adjust Loyalty Points</div>
    <div id="adjustGuest" style="margin-bottom:10px;font-size:.85rem;color:var(--muted);"></div>
    <div class="form-group">
      <label>Delta (positive to add, negative to subtract)</label>
      <input type="number" id="adjustDelta" class="form-control" placeholder="e.g. 100 or -50">
    </div>
    <div class="form-group">
      <label>Reason (required for audit)</label>
      <input type="text" id="adjustNote" class="form-control" placeholder="goodwill credit for cancelled stay">
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="document.getElementById('adjustModal').classList.remove('open')">Cancel</button>
      <button class="btn btn-primary" onclick="submitAdjust()">Apply</button>
    </div>
  </div>
</div>

<script>
const CSRF = '{{ csrf_token }}';
let adjustUserId = null;
function openAdjust(uid, email, current) {
  adjustUserId = uid;
  document.getElementById('adjustGuest').textContent = `${email} — current balance: ${current}`;
  document.getElementById('adjustDelta').value = '';
  document.getElementById('adjustNote').value = '';
  document.getElementById('adjustModal').classList.add('open');
}
function submitAdjust() {
  const delta = parseInt(document.getElementById('adjustDelta').value, 10);
  const note = document.getElementById('adjustNote').value.trim();
  if (!delta || !note) { alert('Delta (non-zero) and note are required.'); return; }
  fetch(`/super-admin/guests/${adjustUserId}/adjust-loyalty/`, {
    method: 'POST',
    headers: {'Content-Type':'application/json','X-CSRFToken': CSRF},
    body: JSON.stringify({delta, note}),
  }).then(r=>r.json()).then(d=>{
    alert(d.message || d.error);
    if (!d.error) location.reload();
  });
}
document.querySelectorAll('.modal-overlay').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.remove('open'); });
});
</script>
{% endblock %}
```

- [ ] **Step 5: Append loyalty-adjust test**

```python
class LoyaltyAdjustTest(TestCase):
    def setUp(self):
        self.sa = _make_super_admin('sa5@x.com')
        self.guest = User.objects.create_user(email='g5@x.com', password='x', is_active=True)
        self.guest.userprofile.role = 'guest'
        self.guest.userprofile.loyalty_points = 100
        self.guest.userprofile.save()

    def test_positive_delta_adds_points_and_logs(self):
        from superadmin.models import AuditLog
        from loyalty.models import LoyaltyLedger
        self.client.force_login(self.sa)
        url = reverse('superadmin:loyalty-adjust', args=[self.guest.pk])
        res = self.client.post(url, data='{"delta":50,"note":"goodwill"}',
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.guest.userprofile.refresh_from_db()
        self.assertEqual(self.guest.userprofile.loyalty_points, 150)
        self.assertTrue(AuditLog.objects.filter(action='LOYALTY_POINTS_ADJUSTED').exists())
        self.assertTrue(LoyaltyLedger.objects.filter(user=self.guest, delta=50).exists())

    def test_zero_delta_rejected(self):
        self.client.force_login(self.sa)
        url = reverse('superadmin:loyalty-adjust', args=[self.guest.pk])
        res = self.client.post(url, data='{"delta":0,"note":"x"}',
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_missing_note_rejected(self):
        self.client.force_login(self.sa)
        url = reverse('superadmin:loyalty-adjust', args=[self.guest.pk])
        res = self.client.post(url, data='{"delta":10,"note":""}',
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_negative_delta_floors_at_zero(self):
        self.client.force_login(self.sa)
        url = reverse('superadmin:loyalty-adjust', args=[self.guest.pk])
        res = self.client.post(url, data='{"delta":-9999,"note":"correction"}',
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.guest.userprofile.refresh_from_db()
        self.assertEqual(self.guest.userprofile.loyalty_points, 0)
```

- [ ] **Step 6: Run the tests**

```bash
python manage.py test superadmin.tests.LoyaltyAdjustTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add superadmin/views.py superadmin/urls.py superadmin/templates/superadmin/ superadmin/tests.py
git commit -m "feat(superadmin): guests page with loyalty point adjustment (audited, ledger-tracked)"
```

---

## Task 6: Employee property reassignment

**Files:**
- Modify: `superadmin/views.py` — extend `employee_update()`
- Modify: `superadmin/templates/superadmin/employees.html` — add properties modal
- Append: `superadmin/tests.py`

- [ ] **Step 1: Extend the `employee_update()` action dispatch**

Find `employee_update()` in `superadmin/views.py`. After the `update_fin` block (before the final `return JsonResponse({'error': 'Unknown action.'}, ...)`), add:

```python
    if action == 'update_properties':
        ids = data.get('property_ids', []) or []
        properties = Property.objects.filter(id__in=ids)
        employee.userprofile.assigned_properties.set(properties)
        names = ', '.join(p.name for p in properties) or '—'
        _log(request, 'PROPERTY_ASSIGNMENT_CHANGED', target_user=employee,
             detail=f"properties→[{names}]")
        return JsonResponse({'message': f'Properties updated: {names}.'})
```

- [ ] **Step 2: Add a property reassignment modal in `superadmin/templates/superadmin/employees.html`**

After the `<!-- Fin Level Modal -->` block, before the `<script>` tag, append:

```html
<!-- Property Reassignment Modal -->
<div class="modal-overlay" id="propModal">
  <div class="modal">
    <div class="modal-title">Reassign Properties</div>
    <div id="propEmail" style="margin-bottom:10px;font-size:.85rem;color:var(--muted);"></div>
    <div class="form-group">
      <label>Assigned Properties</label>
      <select id="prop_select" class="form-control" multiple style="height:140px;">
        {% for prop in properties %}
        <option value="{{ prop.pk }}">{{ prop.name }} — {{ prop.city }}</option>
        {% endfor %}
      </select>
      <small style="color:var(--muted);font-size:.75rem;">Hold Cmd/Ctrl to select multiple</small>
    </div>
    <div class="modal-actions">
      <button class="btn btn-ghost" onclick="document.getElementById('propModal').classList.remove('open')">Cancel</button>
      <button class="btn btn-primary" onclick="submitProps()">Update</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: In the row Actions cell of the same template, add a Properties button**

Find the `<div style="display:flex;gap:6px;flex-wrap:wrap;">` block inside the employees table. After the "Fin Level" button, add:

```html
<button class="btn btn-ghost btn-sm" onclick="openPropModal({{ emp.pk }}, '{{ emp.email }}', '{{ emp.userprofile.assigned_properties.all|join:',' }}')" data-prop-ids="{% for p in emp.userprofile.assigned_properties.all %}{{ p.pk }}{% if not forloop.last %},{% endif %}{% endfor %}">Properties</button>
```

- [ ] **Step 4: Add the JS handlers at the bottom of the existing `<script>` block in `employees.html`**

Append before the closing `</script>`:

```javascript
function openPropModal(uid, email, _) {
  currentEmpId = uid;
  document.getElementById('propEmail').textContent = email;
  const btn = event.currentTarget;
  const ids = (btn.dataset.propIds || '').split(',').filter(Boolean);
  const sel = document.getElementById('prop_select');
  Array.from(sel.options).forEach(o => { o.selected = ids.includes(o.value); });
  document.getElementById('propModal').classList.add('open');
}
function submitProps() {
  const sel = document.getElementById('prop_select');
  const property_ids = Array.from(sel.selectedOptions).map(o => o.value);
  fetch(`/super-admin/employees/${currentEmpId}/update/`, {
    method: 'POST',
    headers: {'Content-Type':'application/json','X-CSRFToken': CSRF},
    body: JSON.stringify({action: 'update_properties', property_ids}),
  }).then(r=>r.json()).then(d=>{
    alert(d.message || d.error);
    if (!d.error) location.reload();
  });
}
```

- [ ] **Step 5: Append property-reassignment test**

```python
class EmployeePropertyAssignmentTest(TestCase):
    def setUp(self):
        self.sa = _make_super_admin('sa6@x.com')
        self.prop_a = Property.objects.create(name='A', city='Pondy', is_active=True)
        self.prop_b = Property.objects.create(name='B', city='Bengaluru', is_active=True)
        self.emp = User.objects.create_user(email='e@x.com', password='x', is_active=True)
        self.emp.userprofile.role = 'employee_admin'
        self.emp.userprofile.save()

    def test_update_properties_replaces_assignment_and_logs(self):
        from superadmin.models import AuditLog
        self.emp.userprofile.assigned_properties.add(self.prop_a)
        self.client.force_login(self.sa)
        url = reverse('superadmin:employee-update', args=[self.emp.pk])
        body = ('{"action":"update_properties","property_ids":["' +
                str(self.prop_b.pk) + '"]}')
        res = self.client.post(url, data=body, content_type='application/json')
        self.assertEqual(res.status_code, 200)
        assigned = list(self.emp.userprofile.assigned_properties.values_list('pk', flat=True))
        self.assertEqual(assigned, [self.prop_b.pk])
        self.assertTrue(AuditLog.objects.filter(action='PROPERTY_ASSIGNMENT_CHANGED').exists())
```

- [ ] **Step 6: Run the test**

```bash
python manage.py test superadmin.tests.EmployeePropertyAssignmentTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 1 PASS.

- [ ] **Step 7: Commit**

```bash
git add superadmin/views.py superadmin/templates/superadmin/employees.html superadmin/tests.py
git commit -m "feat(superadmin): reassign employee properties post-creation (audited)"
```

---

## Final Verification

- [ ] **Run the entire superadmin test suite**

```bash
python manage.py test superadmin --settings=hotel_booking.settings.dev -v 2
```

Expected: every test passes.

- [ ] **Manual smoke test in browser**

Start dev server and step through these scenarios:

| Scenario | Where | Pass when |
|----------|-------|-----------|
| Dashboard glance | `/super-admin/dashboard/` | 4 ops KPIs + 4 revenue KPIs + recent bookings table all render |
| Cancel a booking | `/super-admin/bookings/` → Cancel button | Reason prompt → 200 → row shows "Cancelled"; audit log has BOOKING_CANCELLED with reason |
| Filter bookings | `/super-admin/bookings/?status=confirmed&from=2026-05-01` | Only confirmed bookings from May 1 onward shown |
| Analytics range | `/super-admin/analytics/?from=2026-01-01&to=2026-03-31` | Q1 numbers; occupancy table shows all active properties |
| Change room status | `/super-admin/rooms/` → status dropdown | Cell updates inline; audit log has ROOM_STATUS_UPDATED |
| Adjust loyalty | `/super-admin/guests/` → Adjust Points | Modal → delta + note → success; new balance + tier returned; ledger row appears |
| Reassign properties | `/super-admin/employees/` → Properties button | Modal → multi-select → success; audit log has PROPERTY_ASSIGNMENT_CHANGED |
