# Plan C — EmployeeAdmin Portal Completions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisite:** Plan A must be merged. Plan B is independent — this plan can run in parallel with or after Plan B.

**Goal:** Make the Employee Admin portal genuinely useful for front-desk staff at a single property — booking detail with fin-gated finance info, working room status updates against the new enum, seasonal rate deletion, and a usable booking search/filter UI.

**Architecture:** Same pattern as the existing employeeadmin app — thin views, `@require_employee` decorator, `_assigned_rooms()` for scoping, `_fin_level()` for fin-gating, server-rendered templates with vanilla JS for AJAX.

**Tech Stack:** Django 6, Django ORM, existing `employeeadmin/base.html` design.

---

## Real-world use cases this plan unlocks

| Scenario | Currently | After this plan |
|----------|-----------|-----------------|
| Guest at the desk asks "what time is my checkout?" — front-desk needs booking details | No booking detail view exists | Click row → booking detail page with all info (fin-gated for fin='C') |
| Housekeeping reports "room ready" — front-desk needs to mark Available | Status update sends invalid value, model rejects | Status update works against the four canonical hotel statuses |
| Diwali rate was a typo — needs to be deleted | No rate delete action | Delete button next to each seasonal rate |
| Front-desk searches "guest staying this weekend" | Just 50 latest, no filter | Date range + status filter on bookings list |

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `employeeadmin/views.py` | Modify | Fix `room_status_update` validation; add `seasonal_rate_delete`; add `booking_detail`; add filters to `bookings_list` |
| `employeeadmin/urls.py` | Modify | Add `booking-detail` and `seasonal-rate-delete` URLs |
| `employeeadmin/templates/employeeadmin/rooms.html` | Modify | Status dropdown uses new enum; AJAX call |
| `employeeadmin/templates/employeeadmin/availability.html` | Modify | Add Delete button to seasonal rates table |
| `employeeadmin/templates/employeeadmin/bookings.html` | Modify | Filter form (date range, status); link row to detail |
| `employeeadmin/templates/employeeadmin/booking_detail.html` | Create | New page with fin-gated info |
| `employeeadmin/tests.py` | Append | Tests per task |

---

## Task 1: Fix room status update against new enum

**Prerequisite:** Plan A Task 1 (Room status enum migration) merged.

**Files:**
- Modify: `employeeadmin/views.py` — `room_status_update()`
- Modify: `employeeadmin/templates/employeeadmin/rooms.html` — status dropdown
- Append: `employeeadmin/tests.py`

- [ ] **Step 1: Replace `room_status_update()` in `employeeadmin/views.py`**

```python
@require_employee
@require_POST
def room_status_update(request, room_id):
    room = get_object_or_404(_assigned_rooms(request), pk=room_id)
    new_status = request.POST.get('operational_status') or json.loads(
        request.body or '{}').get('operational_status')
    valid = {choice[0] for choice in Room.OPERATIONAL_STATUS_CHOICES}
    if new_status not in valid:
        return JsonResponse({'error': 'Invalid status.'}, status=400)
    room.operational_status = new_status
    room.save(update_fields=['operational_status'])
    return JsonResponse({'message': f'Status updated to {new_status}.', 'status': new_status})
```

Add `import json` at the top if not already present.

- [ ] **Step 2: Update the status dropdown in `employeeadmin/templates/employeeadmin/rooms.html`**

Find the operational-status cell in the rooms table. Replace the existing dropdown with one driven by the model choices:

```html
<select class="form-control" style="width:160px;" onchange="updateRoomStatus('{{ r.pk }}', this.value, this)">
  <option value="available" {% if r.operational_status == 'available' %}selected{% endif %}>Available</option>
  <option value="cleaning" {% if r.operational_status == 'cleaning' %}selected{% endif %}>Cleaning</option>
  <option value="maintenance" {% if r.operational_status == 'maintenance' %}selected{% endif %}>Maintenance</option>
  <option value="out_of_order" {% if r.operational_status == 'out_of_order' %}selected{% endif %}>Out of Order</option>
</select>
```

If a JS function for the AJAX call doesn't already exist in the template, append in a `<script>` block at the end of the `{% block content %}`:

```html
<script>
const CSRF = '{{ csrf_token }}';
function updateRoomStatus(roomId, value, selectEl) {
  const original = selectEl.dataset.original || selectEl.value;
  fetch(`/admin-portal/rooms/${roomId}/status/`, {
    method: 'POST',
    headers: {'Content-Type':'application/json','X-CSRFToken': CSRF},
    body: JSON.stringify({operational_status: value}),
  }).then(r=>r.json()).then(d=>{
    if (d.error) { alert(d.error); selectEl.value = original; }
    else selectEl.dataset.original = value;
  });
}
document.querySelectorAll('select[onchange*="updateRoomStatus"]').forEach(s => s.dataset.original = s.value);
</script>
```

- [ ] **Step 3: Append test in `employeeadmin/tests.py`**

```python
import json as _json


class EmployeeRoomStatusUpdateTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.room = Room.objects.create(property=self.prop, name='R', city='Pondy',
                                        room_type='single', price_per_night=1000, capacity=2)
        self.emp = User.objects.create_user(email='e2@x.com', password='x', is_active=True)
        self.emp.userprofile.role = 'employee_admin'
        self.emp.userprofile.assigned_properties.add(self.prop)
        self.emp.userprofile.save()

    def test_update_room_status_accepts_canonical_values(self):
        self.client.force_login(self.emp)
        url = reverse('employeeadmin:room-status-update', args=[self.room.pk])
        for s in ['available', 'cleaning', 'maintenance', 'out_of_order']:
            res = self.client.post(url, data=_json.dumps({'operational_status': s}),
                                   content_type='application/json')
            self.assertEqual(res.status_code, 200, msg=f'rejected status: {s}')
            self.room.refresh_from_db()
            self.assertEqual(self.room.operational_status, s)

    def test_update_room_status_rejects_unknown(self):
        self.client.force_login(self.emp)
        url = reverse('employeeadmin:room-status-update', args=[self.room.pk])
        res = self.client.post(url, data=_json.dumps({'operational_status': 'haunted'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_employee_cannot_update_unassigned_room(self):
        other_prop = Property.objects.create(name='Other', city='Bengaluru', is_active=True)
        other_room = Room.objects.create(property=other_prop, name='X', city='Bengaluru',
                                         room_type='single', price_per_night=1000, capacity=2)
        self.client.force_login(self.emp)
        url = reverse('employeeadmin:room-status-update', args=[other_room.pk])
        res = self.client.post(url, data=_json.dumps({'operational_status': 'cleaning'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 404)
```

- [ ] **Step 4: Run the tests**

```bash
python manage.py test employeeadmin.tests.EmployeeRoomStatusUpdateTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add employeeadmin/views.py employeeadmin/templates/employeeadmin/rooms.html employeeadmin/tests.py
git commit -m "fix(employeeadmin): room status update uses Room.OPERATIONAL_STATUS_CHOICES (4 canonical states)"
```

---

## Task 2: Seasonal rate deletion

**Files:**
- Modify: `employeeadmin/views.py` — add `seasonal_rate_delete()`
- Modify: `employeeadmin/urls.py` — add URL
- Modify: `employeeadmin/templates/employeeadmin/availability.html` — add Delete button + JS
- Append: `employeeadmin/tests.py`

- [ ] **Step 1: Append view in `employeeadmin/views.py`**

```python
@require_employee
@require_POST
def seasonal_rate_delete(request, rate_id):
    fin = _fin_level(request)
    if fin == 'C':
        return JsonResponse({'error': 'No financial access.'}, status=403)
    rate = get_object_or_404(RoomRate, pk=rate_id)
    if not _assigned_rooms(request).filter(pk=rate.room_id).exists():
        return JsonResponse({'error': 'Not authorised.'}, status=403)
    rate.delete()
    return JsonResponse({'message': 'Rate removed.'})
```

- [ ] **Step 2: Add URL in `employeeadmin/urls.py`**

```python
path('availability/rate/<uuid:rate_id>/delete/', views.seasonal_rate_delete, name='seasonal-rate-delete'),
```

- [ ] **Step 3: Add Delete button in `employeeadmin/templates/employeeadmin/availability.html`**

Find the seasonal rates table (rendered only when `fin in ('A', 'B')`). Each row currently shows start/end/price. Add an Actions column header and a per-row Delete button. The row should look like:

```html
<tr>
  <td>{{ rate.start_date }}</td>
  <td>{{ rate.end_date }}</td>
  <td>₹{{ rate.price|floatformat:0 }}</td>
  <td><button class="btn btn-danger btn-sm" onclick="deleteRate('{{ rate.pk }}')">Delete</button></td>
</tr>
```

And in the template's script block, add:

```javascript
function deleteRate(rateId) {
  if (!confirm('Delete this seasonal rate?')) return;
  fetch(`/admin-portal/availability/rate/${rateId}/delete/`, {
    method: 'POST',
    headers: {'X-CSRFToken': CSRF},
  }).then(r=>r.json()).then(d=>{
    alert(d.message || d.error);
    if (!d.error) location.reload();
  });
}
```

(`CSRF` should already be defined in the template; if not, add `const CSRF = '{{ csrf_token }}';` at the top of the script block.)

- [ ] **Step 4: Append test**

```python
import datetime
from rooms.models import RoomRate


class SeasonalRateDeleteTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.room = Room.objects.create(property=self.prop, name='R', city='Pondy',
                                        room_type='single', price_per_night=2000, capacity=2)
        self.rate = RoomRate.objects.create(
            room=self.room,
            start_date=datetime.date(2026, 12, 20),
            end_date=datetime.date(2026, 12, 31),
            price=5000,
        )
        self.emp = User.objects.create_user(email='e3@x.com', password='x', is_active=True)
        self.emp.userprofile.role = 'employee_admin'
        self.emp.userprofile.assigned_properties.add(self.prop)
        self.emp.userprofile.fin_level = 'A'
        self.emp.userprofile.save()

    def test_employee_with_fin_a_can_delete(self):
        self.client.force_login(self.emp)
        url = reverse('employeeadmin:seasonal-rate-delete', args=[self.rate.pk])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(RoomRate.objects.filter(pk=self.rate.pk).exists())

    def test_employee_with_fin_c_blocked(self):
        self.emp.userprofile.fin_level = 'C'
        self.emp.userprofile.save()
        self.client.force_login(self.emp)
        url = reverse('employeeadmin:seasonal-rate-delete', args=[self.rate.pk])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 403)

    def test_employee_cannot_delete_unassigned_property_rate(self):
        other_prop = Property.objects.create(name='Other', city='Bengaluru', is_active=True)
        other_room = Room.objects.create(property=other_prop, name='X', city='Bengaluru',
                                         room_type='single', price_per_night=1000, capacity=2)
        other_rate = RoomRate.objects.create(room=other_room,
                                             start_date=datetime.date(2026, 12, 20),
                                             end_date=datetime.date(2026, 12, 31),
                                             price=5000)
        self.client.force_login(self.emp)
        url = reverse('employeeadmin:seasonal-rate-delete', args=[other_rate.pk])
        res = self.client.post(url)
        self.assertEqual(res.status_code, 403)
```

- [ ] **Step 5: Run the tests**

```bash
python manage.py test employeeadmin.tests.SeasonalRateDeleteTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add employeeadmin/views.py employeeadmin/urls.py employeeadmin/templates/employeeadmin/availability.html employeeadmin/tests.py
git commit -m "feat(employeeadmin): delete seasonal rate (fin A/B only, property-scoped)"
```

---

## Task 3: Booking detail view

**Files:**
- Modify: `employeeadmin/views.py` — add `booking_detail()`
- Modify: `employeeadmin/urls.py` — add URL
- Modify: `employeeadmin/templates/employeeadmin/bookings.html` — link reference cell to detail
- Create: `employeeadmin/templates/employeeadmin/booking_detail.html`
- Append: `employeeadmin/tests.py`

- [ ] **Step 1: Append view in `employeeadmin/views.py`**

```python
@require_employee
def booking_detail(request, booking_id):
    fin = _fin_level(request)
    rooms = _assigned_rooms(request)
    booking = get_object_or_404(
        Booking.objects.select_related('user', 'room', 'room__property'),
        pk=booking_id,
        room__in=rooms,
    )
    nights = (booking.check_out - booking.check_in).days
    return render(request, 'employeeadmin/booking_detail.html', {
        'booking': booking,
        'nights': nights,
        'fin': fin,
    })
```

- [ ] **Step 2: Add URL in `employeeadmin/urls.py`**

```python
path('bookings/<uuid:booking_id>/', views.booking_detail, name='booking-detail'),
```

- [ ] **Step 3: Create `employeeadmin/templates/employeeadmin/booking_detail.html`**

```html
{% extends "employeeadmin/base.html" %}
{% block title %}Booking {{ booking.booking_reference }}{% endblock %}
{% block page_title %}Booking — {{ booking.booking_reference }}{% endblock %}
{% block content %}

<a href="{% url 'employeeadmin:bookings' %}" class="btn btn-ghost btn-sm" style="margin-bottom:16px;">← All Bookings</a>

<div class="grid-2" style="margin-bottom:20px;">
  <div class="card">
    <div class="section-head"><h2>Guest</h2></div>
    {% if fin == 'C' %}
      <div style="font-weight:500;"><span class="redacted">████████</span></div>
      <small style="color:var(--muted);">Email and phone redacted (no financial access)</small>
    {% else %}
      <div style="font-weight:500;">{{ booking.user.full_name|default:"—" }}</div>
      <div style="font-size:.85rem;color:var(--muted);">{{ booking.user.email }}</div>
      <div style="font-size:.85rem;color:var(--muted);">{{ booking.user.phone|default:"" }}</div>
    {% endif %}
  </div>

  <div class="card">
    <div class="section-head"><h2>Stay</h2></div>
    <div><strong>Check-in:</strong> {{ booking.check_in }}</div>
    <div><strong>Check-out:</strong> {{ booking.check_out }}</div>
    <div><strong>Nights:</strong> {{ nights }}</div>
    <div><strong>Guests:</strong> {{ booking.guests }}</div>
    <div style="margin-top:8px;">
      <strong>Status:</strong>
      {% if booking.status == 'confirmed' %}<span class="badge badge-success">Confirmed</span>
      {% elif booking.status == 'completed' %}<span class="badge badge-accent">Completed</span>
      {% elif booking.status == 'cancelled' %}<span class="badge badge-danger">Cancelled</span>
      {% else %}<span class="badge badge-muted">{{ booking.status }}</span>{% endif %}
    </div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="section-head"><h2>Room</h2></div>
    <div><strong>{{ booking.room.name }}</strong></div>
    <div style="font-size:.85rem;color:var(--muted);">{{ booking.room.property.name|default:"—" }} / {{ booking.room.city }}</div>
    <div style="font-size:.85rem;color:var(--muted);">Type: {{ booking.room.get_room_type_display }}</div>
    <div style="margin-top:8px;">
      <strong>Operational:</strong>
      {% if booking.room.operational_status == 'available' %}<span class="badge badge-success">Available</span>
      {% elif booking.room.operational_status == 'cleaning' %}<span class="badge badge-yellow">Cleaning</span>
      {% elif booking.room.operational_status == 'maintenance' %}<span class="badge badge-muted">Maintenance</span>
      {% else %}<span class="badge badge-danger">Out of Order</span>{% endif %}
    </div>
  </div>

  <div class="card">
    <div class="section-head"><h2>Payment</h2></div>
    {% if fin == 'C' %}
      <div style="color:var(--muted);">Financial details restricted.</div>
    {% else %}
      <div><strong>Total:</strong> ₹{{ booking.total_price|floatformat:0 }}</div>
      <div><strong>Tax:</strong> ₹{{ booking.tax_amount|default:0|floatformat:0 }}</div>
      {% if booking.razorpay_order_id %}
      <div style="font-size:.8rem;color:var(--muted);margin-top:6px;">Razorpay: {{ booking.razorpay_order_id }}</div>
      {% endif %}
    {% endif %}
  </div>
</div>

{% endblock %}
```

- [ ] **Step 4: Update bookings list template — link the row reference**

In `employeeadmin/templates/employeeadmin/bookings.html`, find the cell that renders `booking_reference` and wrap it as a link:

```html
<td style="font-size:.8rem;font-family:monospace;">
  <a href="{% url 'employeeadmin:booking-detail' b.pk %}" style="color:var(--accent);text-decoration:none;">{{ b.booking_reference }}</a>
</td>
```

- [ ] **Step 5: Append test**

```python
class BookingDetailTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.other_prop = Property.objects.create(name='Other', city='Bengaluru', is_active=True)
        self.room = Room.objects.create(property=self.prop, name='R', city='Pondy',
                                        room_type='single', price_per_night=2000, capacity=2)
        self.other_room = Room.objects.create(property=self.other_prop, name='X', city='Bengaluru',
                                              room_type='single', price_per_night=1000, capacity=2)
        self.guest = User.objects.create_user(email='g@x.com', password='x', is_active=True,
                                              full_name='Test Guest', phone='9999999999')
        today = datetime.date.today()
        self.booking = Booking.objects.create(
            room=self.room, user=self.guest, check_in=today,
            check_out=today + datetime.timedelta(days=2),
            guests=1, status='confirmed', total_price=4000,
        )
        self.other_booking = Booking.objects.create(
            room=self.other_room, user=self.guest, check_in=today,
            check_out=today + datetime.timedelta(days=2),
            guests=1, status='confirmed', total_price=2000,
        )
        self.emp = User.objects.create_user(email='e@x.com', password='x', is_active=True)
        self.emp.userprofile.role = 'employee_admin'
        self.emp.userprofile.assigned_properties.add(self.prop)
        self.emp.userprofile.fin_level = 'A'
        self.emp.userprofile.save()

    def test_employee_sees_assigned_booking_with_full_details(self):
        self.client.force_login(self.emp)
        res = self.client.get(reverse('employeeadmin:booking-detail', args=[self.booking.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Test Guest')
        self.assertContains(res, 'g@x.com')
        self.assertContains(res, '₹4,000') if False else None  # template uses floatformat:0 so "4000"
        self.assertContains(res, '4000')

    def test_employee_cannot_see_unassigned_booking(self):
        self.client.force_login(self.emp)
        res = self.client.get(reverse('employeeadmin:booking-detail', args=[self.other_booking.pk]))
        self.assertEqual(res.status_code, 404)

    def test_fin_c_employee_sees_redacted_guest_and_no_payment(self):
        self.emp.userprofile.fin_level = 'C'
        self.emp.userprofile.save()
        self.client.force_login(self.emp)
        res = self.client.get(reverse('employeeadmin:booking-detail', args=[self.booking.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, 'g@x.com')
        self.assertNotContains(res, '4000')
```

- [ ] **Step 6: Run the tests**

```bash
python manage.py test employeeadmin.tests.BookingDetailTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add employeeadmin/views.py employeeadmin/urls.py employeeadmin/templates/employeeadmin/ employeeadmin/tests.py
git commit -m "feat(employeeadmin): booking detail page (property-scoped, fin-gated)"
```

---

## Task 4: Bookings list — filters

**Files:**
- Modify: `employeeadmin/views.py` — `bookings_list()`
- Modify: `employeeadmin/templates/employeeadmin/bookings.html`
- Append: `employeeadmin/tests.py`

- [ ] **Step 1: Replace `bookings_list()`**

```python
@require_employee
def bookings_list(request):
    fin = _fin_level(request)
    rooms = _assigned_rooms(request)

    qs = Booking.objects.filter(room__in=rooms).select_related(
        'user', 'room', 'room__property').order_by('-check_in')

    status = request.GET.get('status', '').strip()
    from_date = request.GET.get('from', '').strip()
    to_date = request.GET.get('to', '').strip()
    q = request.GET.get('q', '').strip()

    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.filter(status__in=('confirmed', 'completed', 'cancelled'))
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

    return render(request, 'employeeadmin/bookings.html', {
        'bookings': qs[:100],
        'fin': fin,
        'selected': {'status': status, 'from': from_date, 'to': to_date, 'q': q},
        'status_choices': [
            ('', 'All (excl. pending/expired)'),
            ('confirmed', 'Confirmed'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
    })
```

Add `from django.db.models import Q` at the top of the file if not already imported.

- [ ] **Step 2: Add filter form to `employeeadmin/templates/employeeadmin/bookings.html`**

Before the existing bookings table card, insert:

```html
<form method="get" class="card" style="margin-bottom:16px;">
  <div style="display:grid;grid-template-columns:2fr 1fr 1fr 1fr auto;gap:10px;align-items:end;">
    <div class="form-group" style="margin:0;">
      <label>Search (ref / guest)</label>
      <input type="text" name="q" class="form-control" value="{{ selected.q }}" placeholder="TT-2026-... or email">
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
```

- [ ] **Step 3: Append filter test**

```python
class BookingsFilterTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.room = Room.objects.create(property=self.prop, name='R', city='Pondy',
                                        room_type='single', price_per_night=1000, capacity=2)
        self.guest = User.objects.create_user(email='g@x.com', password='x', is_active=True)
        Booking.objects.create(room=self.room, user=self.guest,
                               check_in=datetime.date(2026, 5, 1),
                               check_out=datetime.date(2026, 5, 3),
                               guests=1, status='confirmed', total_price=2000)
        Booking.objects.create(room=self.room, user=self.guest,
                               check_in=datetime.date(2026, 6, 1),
                               check_out=datetime.date(2026, 6, 3),
                               guests=1, status='cancelled', total_price=2000)
        self.emp = User.objects.create_user(email='e@x.com', password='x', is_active=True)
        self.emp.userprofile.role = 'employee_admin'
        self.emp.userprofile.assigned_properties.add(self.prop)
        self.emp.userprofile.save()

    def test_status_filter_works(self):
        self.client.force_login(self.emp)
        url = reverse('employeeadmin:bookings') + '?status=cancelled'
        res = self.client.get(url)
        self.assertEqual(len(res.context['bookings']), 1)
        self.assertEqual(res.context['bookings'][0].status, 'cancelled')

    def test_date_filter_works(self):
        self.client.force_login(self.emp)
        url = reverse('employeeadmin:bookings') + '?from=2026-05-01&to=2026-05-31'
        res = self.client.get(url)
        self.assertEqual(len(res.context['bookings']), 1)
        self.assertEqual(res.context['bookings'][0].check_in.month, 5)
```

- [ ] **Step 4: Run the tests**

```bash
python manage.py test employeeadmin.tests.BookingsFilterTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add employeeadmin/views.py employeeadmin/templates/employeeadmin/bookings.html employeeadmin/tests.py
git commit -m "feat(employeeadmin): bookings list with status + date + text filters"
```

---

## Final Verification

- [ ] **Run the full employeeadmin test suite**

```bash
python manage.py test employeeadmin --settings=hotel_booking.settings.dev -v 2
```

Expected: every test passes.

- [ ] **Manual smoke test**

Log in as an employee_admin (with at least one property assigned and fin_level='A'). Walk through:

| Scenario | Where | Pass when |
|----------|-------|-----------|
| Status update | `/admin-portal/rooms/` → status dropdown | Picks Cleaning / Maintenance / Out of Order → inline persist; refresh keeps value |
| Filter bookings | `/admin-portal/bookings/?status=cancelled` | Only cancelled bookings for assigned property |
| Open booking detail | Click reference in bookings list | Detail page with guest + stay + room + payment cards |
| Booking detail isolation | Manually visit a booking URL for an unassigned property | 404 |
| Delete seasonal rate | `/admin-portal/availability/?room=...` (with fin A or B) | Delete button removes the row |
| Fin C lockdown | Switch to a fin='C' employee, visit booking detail | Guest email + payment cards hidden/redacted |
