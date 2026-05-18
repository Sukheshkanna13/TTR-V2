# Plan D — Operational Dashboards & Full Access Control

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both admin portals fully operational — dashboards become action surfaces, not just viewers. Superadmin owns all access control. EmployeeAdmin can manage their property's daily operations from their dashboard.

**Architecture:** No new models needed. All backend logic from Plans A/B/C stays. This plan wires operational buttons to existing endpoints and adds the missing ones (employeeadmin booking_complete, employee property assignment, guests/loyalty page).

**Tech Stack:** Django 6, AJAX fetch + CSRF token pattern (established in bookings.html), existing `_log()` helper for audit.

**Business rule:** Employees cannot change their own passwords. Only superadmin can reset them via the employees page. The `must_change_password` redirect in `get_post_login_redirect()` must be removed for admin roles.

---

## What's already built (do not re-implement)

| Endpoint | Status |
|----------|--------|
| `POST /superadmin/bookings/<id>/cancel/` | ✅ Done |
| `POST /superadmin/bookings/<id>/complete/` | ✅ Done |
| `POST /superadmin/rooms/<id>/update/` | ✅ Done (set_status + toggle_active) |
| `POST /superadmin/employees/<id>/update/` | ✅ Done (lock/unlock/reset_password/update_fin) |
| `_assigned_rooms()` security fix | ✅ Done |
| Dashboard + bookings scoped to assigned properties | ✅ Done |

---

## Task 1: Fix login flow — remove must_change_password block for admin roles

**Files:**
- Modify: `accounts/role_routing.py` — `get_post_login_redirect()`

- [ ] **Step 1: Update `get_post_login_redirect()` in `accounts/role_routing.py`**

Current (blocks employee admins from reaching their dashboard):
```python
def get_post_login_redirect(user, next_url=None):
    if must_change_password(user):
        return CHANGE_PASSWORD_URL
    ...
```

Replace with (only redirect guests to change-password, admins go straight to dashboard):
```python
def get_post_login_redirect(user, next_url=None):
    role = get_user_role(user)
    # Only guests see the change-password redirect; admin roles go straight to their dashboard.
    if role == ROLE_GUEST and must_change_password(user):
        return CHANGE_PASSWORD_URL

    if next_url and is_role_allowed_for_path(role, next_url):
        return next_url

    return get_default_redirect_for_role(role)
```

- [ ] **Step 2: Test manually** — create an employee with `must_change_password=True`, log in, verify they land on `/admin-portal/dashboard/` not `/accounts/change-password/`.

- [ ] **Step 3: Commit**
```bash
git add accounts/role_routing.py
git commit -m "fix: admin roles skip must_change_password redirect — only guests are redirected"
```

---

## Task 2: Superadmin dashboard — interactive operational lists

**Files:**
- Modify: `superadmin/views.py` — `dashboard()`
- Modify: `templates/superadmin/dashboard.html`

- [ ] **Step 1: Update `dashboard()` to pass querysets (not just counts) for today's operations**

Replace the count-only fields with querysets in `superadmin/views.py`:

```python
@require_super_admin
def dashboard(request):
    today = timezone.now().date()
    month_start = today.replace(day=1)

    active_bookings = Booking.objects.filter(
        status='confirmed', check_in__lte=today, check_out__gt=today,
    ).count()

    todays_arrivals = Booking.objects.filter(
        status='confirmed', check_in=today,
    ).select_related('user', 'room__property')

    todays_departures = Booking.objects.filter(
        status='confirmed', check_out=today,
    ).select_related('user', 'room__property')

    pending_holds = Booking.objects.filter(
        status='pending',
    ).select_related('user', 'room__property').order_by('created_at')[:20]

    today_revenue = todays_arrivals.aggregate(t=Sum('total_price'))['t'] or 0

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
        'todays_checkins': todays_arrivals.count(),
        'todays_checkouts': todays_departures.count(),
        'today_revenue': today_revenue,
        'month_revenue': month_revenue,
        'total_rooms': total_rooms,
        'total_guests': total_guests,
        'recent_bookings': recent_bookings,
    })
```

- [ ] **Step 2: Rewrite `templates/superadmin/dashboard.html`**

Add three operational tables below the KPI stats row. Each row has inline action buttons that call the existing AJAX endpoints.

```html
{% extends "superadmin/base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h1 class="sa-page-title">Dashboard</h1>

<!-- KPI strip -->
<div class="sa-card">
  <div class="sa-stats">
    <div class="sa-stat">
      <div class="sa-stat-val">{{ active_bookings }}</div>
      <div class="sa-stat-label">Active stays</div>
    </div>
    <div class="sa-stat">
      <div class="sa-stat-val">{{ todays_checkins }}</div>
      <div class="sa-stat-label">Check-ins today</div>
    </div>
    <div class="sa-stat">
      <div class="sa-stat-val">{{ todays_checkouts }}</div>
      <div class="sa-stat-label">Check-outs today</div>
    </div>
    <div class="sa-stat">
      <div class="sa-stat-val">{{ pending_holds.count }}</div>
      <div class="sa-stat-label">Pending holds</div>
    </div>
    <div class="sa-stat">
      <div class="sa-stat-val">₹{{ today_revenue|floatformat:0 }}</div>
      <div class="sa-stat-label">Today revenue</div>
    </div>
    <div class="sa-stat">
      <div class="sa-stat-val">₹{{ month_revenue|floatformat:0 }}</div>
      <div class="sa-stat-label">This month</div>
    </div>
    <div class="sa-stat">
      <div class="sa-stat-val">{{ total_rooms }}</div>
      <div class="sa-stat-label">Total rooms</div>
    </div>
    <div class="sa-stat">
      <div class="sa-stat-val">{{ total_guests }}</div>
      <div class="sa-stat-label">Guests</div>
    </div>
  </div>
</div>

<!-- Today's arrivals -->
<div class="sa-card" style="margin-top:1.5rem">
  <h2 class="sa-section-title">Today's Arrivals</h2>
  <table class="sa-table">
    <thead><tr><th>Ref</th><th>Guest</th><th>Room</th><th>Property</th><th>Check-out</th><th>Amount</th><th>Action</th></tr></thead>
    <tbody>
    {% for b in todays_arrivals %}
    <tr id="arr-{{ b.id }}">
      <td><code>{{ b.booking_reference }}</code></td>
      <td>{{ b.user.full_name }}</td>
      <td>{{ b.room.name }}</td>
      <td>{{ b.room.property.name }}</td>
      <td>{{ b.check_out }}</td>
      <td>₹{{ b.total_price|floatformat:0 }}</td>
      <td>
        <button class="sa-btn sa-btn-sm sa-btn-success" onclick="completeBooking('{{ b.id }}', 'arr')">Check in ✓</button>
      </td>
    </tr>
    {% empty %}
    <tr><td colspan="7" style="color:#64748b;padding:16px">No arrivals today.</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<!-- Today's departures -->
<div class="sa-card" style="margin-top:1.5rem">
  <h2 class="sa-section-title">Today's Departures</h2>
  <table class="sa-table">
    <thead><tr><th>Ref</th><th>Guest</th><th>Room</th><th>Property</th><th>Check-in</th><th>Amount</th><th>Action</th></tr></thead>
    <tbody>
    {% for b in todays_departures %}
    <tr id="dep-{{ b.id }}">
      <td><code>{{ b.booking_reference }}</code></td>
      <td>{{ b.user.full_name }}</td>
      <td>{{ b.room.name }}</td>
      <td>{{ b.room.property.name }}</td>
      <td>{{ b.check_in }}</td>
      <td>₹{{ b.total_price|floatformat:0 }}</td>
      <td>
        <button class="sa-btn sa-btn-sm sa-btn-success" onclick="completeBooking('{{ b.id }}', 'dep')">Check out ✓</button>
      </td>
    </tr>
    {% empty %}
    <tr><td colspan="7" style="color:#64748b;padding:16px">No departures today.</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<!-- Pending holds -->
<div class="sa-card" style="margin-top:1.5rem">
  <h2 class="sa-section-title">Pending Holds</h2>
  <table class="sa-table">
    <thead><tr><th>Ref</th><th>Guest</th><th>Room</th><th>Property</th><th>Check-in</th><th>Expires</th><th>Action</th></tr></thead>
    <tbody>
    {% for b in pending_holds %}
    <tr id="hold-{{ b.id }}">
      <td><code>{{ b.booking_reference }}</code></td>
      <td>{{ b.user.full_name }}</td>
      <td>{{ b.room.name }}</td>
      <td>{{ b.room.property.name }}</td>
      <td>{{ b.check_in }}</td>
      <td>{{ b.hold_expires_at|default:"—" }}</td>
      <td>
        <button class="sa-btn sa-btn-sm sa-btn-danger" onclick="cancelBooking('{{ b.id }}', 'hold')">Cancel hold</button>
      </td>
    </tr>
    {% empty %}
    <tr><td colspan="7" style="color:#64748b;padding:16px">No pending holds.</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<!-- Recent bookings -->
{% if recent_bookings %}
<div class="sa-card" style="margin-top:1.5rem">
  <h2 class="sa-section-title">Recent Bookings</h2>
  <table class="sa-table">
    <thead><tr><th>Ref</th><th>Guest</th><th>Room</th><th>Property</th><th>Check-in</th><th>Check-out</th><th>Status</th><th>Amount</th></tr></thead>
    <tbody>
    {% for b in recent_bookings %}
    <tr>
      <td><code>{{ b.booking_reference|default:b.id }}</code></td>
      <td>{{ b.user.full_name }}</td>
      <td>{{ b.room.name }}</td>
      <td>{{ b.room.property.name }}</td>
      <td>{{ b.check_in }}</td>
      <td>{{ b.check_out }}</td>
      <td><span class="sa-badge sa-badge-{{ b.status }}">{{ b.status }}</span></td>
      <td>₹{{ b.total_price|floatformat:0 }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<script>
const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

async function completeBooking(id, prefix) {
  if (!confirm('Mark as completed?')) return;
  const res = await fetch(`/superadmin/bookings/${id}/complete/`, {
    method: 'POST', headers: {'X-CSRFToken': csrf},
  });
  const data = await res.json();
  if (res.ok) {
    document.getElementById(prefix + '-' + id)?.remove();
    alert(data.message);
  } else alert(data.error);
}

async function cancelBooking(id, prefix) {
  const reason = prompt('Cancellation reason (optional):');
  if (reason === null) return;
  const fd = new FormData();
  fd.append('reason', reason);
  const res = await fetch(`/superadmin/bookings/${id}/cancel/`, {
    method: 'POST', headers: {'X-CSRFToken': csrf}, body: fd,
  });
  const data = await res.json();
  if (res.ok) {
    document.getElementById(prefix + '-' + id)?.remove();
    alert(data.message);
  } else alert(data.error);
}
</script>
{% endblock %}
```

- [ ] **Step 3: Check `hold_expires_at` field name on Booking model**

```bash
grep -n "hold_expires_at\|expires_at" rooms/models.py
```

Use the correct field name in the template.

- [ ] **Step 4: Commit**
```bash
git add superadmin/views.py templates/superadmin/dashboard.html
git commit -m "feat(superadmin): operational dashboard — arrivals, departures, holds with inline actions"
```

---

## Task 3: Superadmin employees — property assignment modal

**Files:**
- Modify: `superadmin/views.py` — `employee_update()`, add `update_properties` action
- Modify: `templates/superadmin/employees.html` — add Properties button + modal

- [ ] **Step 1: Add `update_properties` action to `employee_update()` in `superadmin/views.py`**

Inside the `employee_update()` function, after the existing `update_fin` block:
```python
    if action == 'update_properties':
        property_ids = data.get('property_ids', [])
        profile = employee.userprofile
        profile.assigned_properties.set(
            Property.objects.filter(id__in=property_ids)
        )
        _log(request, 'PROPERTY_ASSIGNMENT_CHANGED', target_user=employee,
             detail=f"properties={property_ids}")
        return JsonResponse({'message': 'Properties updated.'})
```

- [ ] **Step 2: Add Properties column and modal in `templates/superadmin/employees.html`**

Add a "Properties" button in each employee row that opens a modal with checkboxes for all active properties. On save, POST to `employee_update()` with `action=update_properties`.

HTML additions (inside the employee row `<td>` actions cell):
```html
<button class="sa-btn sa-btn-sm" onclick="openPropertiesModal('{{ emp.id }}', {{ emp.userprofile.assigned_properties.all|json_script:None }})">Properties</button>
```

Modal at bottom of template:
```html
<div id="props-modal" style="display:none;" class="sa-modal-overlay">
  <div class="sa-modal">
    <h3>Assign Properties</h3>
    <input type="hidden" id="props-emp-id">
    <div id="props-checkboxes"></div>
    <div style="margin-top:1rem;display:flex;gap:.5rem">
      <button class="sa-btn sa-btn-primary" onclick="saveProperties()">Save</button>
      <button class="sa-btn" onclick="document.getElementById('props-modal').style.display='none'">Cancel</button>
    </div>
  </div>
</div>
```

Pass all properties to template in `employees_list()` (already done — `properties` context var exists).

JS to render checkboxes and save:
```javascript
const allProperties = {{ properties|safe }};  // JSON list from view

function openPropertiesModal(empId, assignedIds) {
  document.getElementById('props-emp-id').value = empId;
  const box = document.getElementById('props-checkboxes');
  box.innerHTML = allProperties.map(p =>
    `<label style="display:block;margin:.25rem 0">
      <input type="checkbox" value="${p.id}" ${assignedIds.includes(p.id) ? 'checked' : ''}> ${p.name}
    </label>`
  ).join('');
  document.getElementById('props-modal').style.display = 'flex';
}

async function saveProperties() {
  const empId = document.getElementById('props-emp-id').value;
  const ids = [...document.querySelectorAll('#props-checkboxes input:checked')].map(c => c.value);
  const res = await fetch(`/superadmin/employees/${empId}/update/`, {
    method: 'POST',
    headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/json'},
    body: JSON.stringify({action: 'update_properties', property_ids: ids}),
  });
  const data = await res.json();
  alert(data.message || data.error);
  document.getElementById('props-modal').style.display = 'none';
}
```

Note: The `employees_list()` view must pass `properties` as a JSON-serializable list for the JS. Modify the view to pass:
```python
import json as _json
properties_json = _json.dumps([{'id': str(p.id), 'name': p.name} for p in properties])
```
And pass `properties_json` to template context.

- [ ] **Step 3: Commit**
```bash
git add superadmin/views.py templates/superadmin/employees.html
git commit -m "feat(superadmin): employee property assignment modal"
```

---

## Task 4: Superadmin — Guests/Loyalty page

**Files:**
- Modify: `superadmin/views.py` — add `guests_list()` and `loyalty_adjust()`
- Create: `templates/superadmin/guests.html`
- Modify: `superadmin/urls.py`

- [ ] **Step 1: Add views to `superadmin/views.py`**

```python
# ── Guests / Loyalty ───────────────────────────────────────────────────────────

@require_super_admin
def guests_list(request):
    q = request.GET.get('q', '').strip()
    guests = User.objects.filter(userprofile__role='guest').select_related('userprofile').order_by('-date_joined')
    if q:
        guests = guests.filter(
            Q(full_name__icontains=q) | Q(email__icontains=q)
        )
    return render(request, 'superadmin/guests.html', {'guests': guests[:100], 'q': q})


@require_super_admin
@require_POST
def loyalty_adjust(request, user_id):
    from loyalty.models import LoyaltyLedger
    guest = get_object_or_404(User, pk=user_id)
    data = json.loads(request.body)
    delta = int(data.get('delta', 0))
    reason = data.get('reason', '').strip()
    if not reason:
        return JsonResponse({'error': 'Reason required.'}, status=400)
    if delta == 0:
        return JsonResponse({'error': 'Delta cannot be zero.'}, status=400)

    LoyaltyLedger.objects.create(
        user=guest,
        delta=delta,
        reason='admin_adjustment',
        note=reason,
    )
    guest.userprofile.loyalty_points = max(0, guest.userprofile.loyalty_points + delta)
    guest.userprofile.save(update_fields=['loyalty_points'])
    _log(request, 'LOYALTY_POINTS_ADJUSTED', target_user=guest,
         detail=f"delta={delta}, reason={reason}")
    return JsonResponse({'message': f'Adjusted {delta:+} points.', 'new_total': guest.userprofile.loyalty_points})
```

- [ ] **Step 2: Check LoyaltyLedger model fields**

```bash
grep -n "class LoyaltyLedger\|delta\|reason\|note" loyalty/models.py | head -10
```

Adjust field names if different.

- [ ] **Step 3: Create `templates/superadmin/guests.html`**

```html
{% extends "superadmin/base.html" %}
{% block title %}Guests{% endblock %}
{% block content %}
<h1 class="sa-page-title">Guests</h1>

<div class="sa-card" style="margin-bottom:1rem">
  <form method="get" style="display:flex;gap:.75rem;align-items:flex-end">
    <div>
      <label class="sa-label">Search</label>
      <input class="sa-input" type="text" name="q" value="{{ q }}" placeholder="Name or email">
    </div>
    <button class="sa-btn sa-btn-primary" type="submit">Search</button>
    <a class="sa-btn" href="{% url 'superadmin:guests' %}">Clear</a>
  </form>
</div>

<div class="sa-card">
  <table class="sa-table">
    <thead>
      <tr><th>Name</th><th>Email</th><th>Joined</th><th>Loyalty points</th><th>Actions</th></tr>
    </thead>
    <tbody>
    {% for g in guests %}
    <tr>
      <td>{{ g.full_name }}</td>
      <td>{{ g.email }}</td>
      <td>{{ g.date_joined|date:"d M Y" }}</td>
      <td id="pts-{{ g.id }}">{{ g.userprofile.loyalty_points }}</td>
      <td>
        <button class="sa-btn sa-btn-sm" onclick="adjustLoyalty('{{ g.id }}', '{{ g.full_name|escapejs }}')">Adjust points</button>
      </td>
    </tr>
    {% empty %}
    <tr><td colspan="5" style="color:#64748b;padding:24px">No guests found.</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<script>
const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

async function adjustLoyalty(userId, name) {
  const delta = parseInt(prompt(`Adjust points for ${name} (use negative to deduct):`));
  if (isNaN(delta) || delta === 0) return;
  const reason = prompt('Reason for adjustment:');
  if (!reason) return;
  const res = await fetch(`/superadmin/guests/${userId}/adjust-loyalty/`, {
    method: 'POST',
    headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/json'},
    body: JSON.stringify({delta, reason}),
  });
  const data = await res.json();
  if (res.ok) {
    document.getElementById('pts-' + userId).textContent = data.new_total;
    alert(data.message);
  } else alert(data.error);
}
</script>
{% endblock %}
```

- [ ] **Step 4: Add URLs to `superadmin/urls.py`**

```python
path('guests/', views.guests_list, name='guests'),
path('guests/<int:user_id>/adjust-loyalty/', views.loyalty_adjust, name='loyalty-adjust'),
```

- [ ] **Step 5: Commit**
```bash
git add superadmin/views.py superadmin/urls.py templates/superadmin/guests.html
git commit -m "feat(superadmin): guests list with loyalty point adjustment"
```

---

## Task 5: EmployeeAdmin dashboard — interactive check-in/check-out

**Files:**
- Modify: `employeeadmin/views.py` — add `booking_complete()`
- Modify: `employeeadmin/urls.py`
- Modify: `templates/employeeadmin/dashboard.html`

- [ ] **Step 1: Check current employeeadmin dashboard template**

```bash
cat templates/employeeadmin/dashboard.html
```

- [ ] **Step 2: Add `booking_complete()` to `employeeadmin/views.py`**

```python
@require_employee
@require_POST
def booking_complete(request, booking_id):
    rooms = _assigned_rooms(request)
    booking = get_object_or_404(Booking, pk=booking_id, room__in=rooms)
    if booking.status != 'confirmed':
        return JsonResponse({'error': 'Only confirmed bookings can be marked completed.'}, status=400)
    booking.status = 'completed'
    booking.save(update_fields=['status'])
    return JsonResponse({'message': 'Booking marked as completed.'})
```

- [ ] **Step 3: Add URL to `employeeadmin/urls.py`**

```python
path('bookings/<uuid:booking_id>/complete/', views.booking_complete, name='booking-complete'),
```

- [ ] **Step 4: Update `templates/employeeadmin/dashboard.html`**

Add action column to upcoming_checkins and upcoming_checkouts tables with "Complete" button calling the AJAX endpoint.

Dashboard view already passes `upcoming_checkins` and `upcoming_checkouts` as scoped querysets. Add select_related to include room data.

- [ ] **Step 5: Commit**
```bash
git add employeeadmin/views.py employeeadmin/urls.py templates/employeeadmin/dashboard.html
git commit -m "feat(employeeadmin): interactive dashboard — complete check-in/check-out inline"
```

---

## Task 6: Add navigation links for new pages

**Files:**
- Modify: `templates/superadmin/base.html` — add Rooms and Guests nav links
- Modify: `templates/employeeadmin/base.html` — verify all nav links present

- [ ] **Step 1: Check superadmin base.html nav**

```bash
grep -n "href\|nav" templates/superadmin/base.html
```

- [ ] **Step 2: Add Rooms and Guests links to superadmin nav**

```html
<a href="{% url 'superadmin:rooms' %}" class="sa-nav-link">Rooms</a>
<a href="{% url 'superadmin:guests' %}" class="sa-nav-link">Guests</a>
```

- [ ] **Step 3: Commit**
```bash
git add templates/superadmin/base.html
git commit -m "feat(superadmin): add Rooms and Guests navigation links"
```

---

## Final Verification

- [ ] Run full test suite: `python manage.py test --settings=hotel_booking.settings.dev`
- [ ] Start dev server and verify superadmin dashboard shows arrivals/departures/holds tables
- [ ] Verify employee admin login with temp password goes directly to dashboard (no change-password redirect)
- [ ] Verify employee admin dashboard shows only assigned property bookings with Complete buttons
- [ ] Verify superadmin can assign properties to employee from employees page
- [ ] Verify superadmin guests page loads and loyalty adjustment writes to DB
