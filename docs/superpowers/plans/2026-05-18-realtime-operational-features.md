# Real-Time Operational Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live operational awareness to both the Superadmin and Employee dashboards — countdown timers on holds, AJAX-polling KPI refresh, and a room-status board — all without adding new backend dependencies.

**Architecture:** Pure AJAX polling via `fetch` + `setInterval`. New JSON endpoints return structured snapshots; JS updates the DOM in-place. Client-side JS handles hold countdowns from ISO timestamps emitted by the server. No WebSockets, no Channels, no Redis.

**Tech Stack:** Django 6 MVT · Vanilla JS (no libraries) · `JsonResponse` · existing `rooms.models.Booking` / `Room` models

---

## File Map

| File | Change |
|------|--------|
| `superadmin/views.py` | Add `dashboard_live_data`, `room_status_board` JSON + render views |
| `superadmin/urls.py` | Add `/dashboard/live/`, `/rooms/status-board/` routes |
| `employeeadmin/views.py` | Add `dashboard_live_data`, `room_status_board` JSON + render views |
| `employeeadmin/urls.py` | Add `/dashboard/live/`, `/rooms/status-board/` routes |
| `templates/superadmin/dashboard.html` | Wire `hold_expires_at` timestamps into JS countdown; add poll loop |
| `templates/employeeadmin/dashboard.html` | Same countdown + poll wiring for employee scope |
| `templates/superadmin/room_status_board.html` | New: colour-coded room grid with inline status dropdown + 60s auto-refresh |
| `templates/employeeadmin/room_status_board.html` | New: same grid, scoped to assigned rooms only |
| `superadmin/tests.py` | Tests for `dashboard_live_data` and `room_status_board` JSON views |
| `employeeadmin/tests.py` | Tests for employee-scoped equivalents |

---

## Task 1: Superadmin — `dashboard_live_data` JSON endpoint

**Files:**
- Modify: `superadmin/views.py`
- Modify: `superadmin/urls.py`
- Modify: `superadmin/tests.py`

This endpoint returns a JSON snapshot of dashboard KPIs + pending holds list for the polling loop.

- [ ] **Step 1: Write the failing test**

```python
# superadmin/tests.py  — add inside existing TestCase or create one
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from rooms.models import Property, Room, Booking
from superadmin.models import AuditLog

User = get_user_model()


class DashboardLiveDataTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email='sa@test.com', full_name='SA', phone='0000000000',
            password='pass',
        )
        from accounts.models import UserProfile
        UserProfile.objects.filter(user=self.admin).update(role='super_admin')
        self.client.force_login(self.admin)

    def test_live_data_returns_json(self):
        res = self.client.get(reverse('superadmin:dashboard-live'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('active_bookings', data)
        self.assertIn('pending_holds', data)
        self.assertIn('todays_checkins', data)
        self.assertIn('todays_checkouts', data)
        self.assertIn('today_revenue', data)

    def test_pending_holds_include_expires_at(self):
        res = self.client.get(reverse('superadmin:dashboard-live'))
        data = res.json()
        # list may be empty — structure is still valid
        self.assertIsInstance(data['pending_holds'], list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test superadmin.tests.DashboardLiveDataTest -v 2
```

Expected: `FAIL — NoReverseMatch` or `AttributeError` (view not defined yet).

- [ ] **Step 3: Add the view to `superadmin/views.py`**

Add at the end of the Dashboard section (after the existing `dashboard` function):

```python
@require_super_admin
def dashboard_live_data(request):
    today = timezone.now().date()
    month_start = today.replace(day=1)

    active_bookings = Booking.objects.filter(
        status='confirmed', check_in__lte=today, check_out__gt=today,
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

    holds_qs = Booking.objects.filter(status='pending').select_related(
        'user', 'room__property',
    ).order_by('created_at')[:20]

    pending_holds = [
        {
            'id': str(b.id),
            'reference': b.booking_reference or str(b.id)[:8],
            'guest': b.user.full_name or b.user.email,
            'room': b.room.name,
            'property': b.room.property.name,
            'check_in': str(b.check_in),
            'expires_at': b.hold_expires_at.isoformat() if b.hold_expires_at else None,
        }
        for b in holds_qs
    ]

    return JsonResponse({
        'active_bookings': active_bookings,
        'todays_checkins': todays_checkins,
        'todays_checkouts': todays_checkouts,
        'today_revenue': float(today_revenue),
        'pending_holds': pending_holds,
    })
```

- [ ] **Step 4: Add URL to `superadmin/urls.py`**

```python
path('dashboard/live/', views.dashboard_live_data, name='dashboard-live'),
```

Place it directly after the existing `dashboard/` path.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python manage.py test superadmin.tests.DashboardLiveDataTest -v 2
```

Expected: all 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add superadmin/views.py superadmin/urls.py superadmin/tests.py
git commit -m "feat(superadmin): dashboard live-data JSON endpoint"
```

---

## Task 2: Employee Admin — `dashboard_live_data` JSON endpoint

**Files:**
- Modify: `employeeadmin/views.py`
- Modify: `employeeadmin/urls.py`
- Modify: `employeeadmin/tests.py`

Same shape as Task 1 but scoped to the employee's assigned properties.

- [ ] **Step 1: Write the failing test**

```python
# employeeadmin/tests.py — add to existing file
class EmployeeDashboardLiveDataTest(TestCase):
    def setUp(self):
        self.client = Client()
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        User = get_user_model()
        self.emp = User.objects.create_user(
            email='emp@test.com', full_name='Emp', phone='1111111111',
            password='pass',
        )
        UserProfile.objects.filter(user=self.emp).update(role='employee')
        self.client.force_login(self.emp)

    def test_live_data_returns_json(self):
        res = self.client.get(reverse('employeeadmin:dashboard-live'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('active_bookings', data)
        self.assertIn('todays_checkins', data)
        self.assertIn('todays_checkouts', data)

    def test_employee_with_no_properties_sees_zero_counts(self):
        res = self.client.get(reverse('employeeadmin:dashboard-live'))
        data = res.json()
        self.assertEqual(data['active_bookings'], 0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test employeeadmin.tests.EmployeeDashboardLiveDataTest -v 2
```

Expected: FAIL — `NoReverseMatch`.

- [ ] **Step 3: Add the view to `employeeadmin/views.py`**

Add after the existing `dashboard` function:

```python
@require_employee
def dashboard_live_data(request):
    today = timezone.now().date()
    rooms = _assigned_rooms(request)

    bookings_qs = Booking.objects.filter(room__in=rooms, status='confirmed')

    active_bookings = bookings_qs.filter(
        check_in__lte=today, check_out__gt=today,
    ).count()

    todays_checkins = bookings_qs.filter(check_in=today).count()
    todays_checkouts = bookings_qs.filter(check_out=today).count()

    return JsonResponse({
        'active_bookings': active_bookings,
        'todays_checkins': todays_checkins,
        'todays_checkouts': todays_checkouts,
    })
```

- [ ] **Step 4: Add URL to `employeeadmin/urls.py`**

```python
path('dashboard/live/', views.dashboard_live_data, name='dashboard-live'),
```

Place it directly after the existing `dashboard/` path.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python manage.py test employeeadmin.tests.EmployeeDashboardLiveDataTest -v 2
```

Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add employeeadmin/views.py employeeadmin/urls.py employeeadmin/tests.py
git commit -m "feat(employeeadmin): dashboard live-data JSON endpoint"
```

---

## Task 3: Superadmin Dashboard — Hold Countdown + KPI Auto-Refresh

**Files:**
- Modify: `templates/superadmin/dashboard.html`

No backend changes. Wire the `hold_expires_at` timestamps emitted in the existing HTML into live JS countdowns, and poll `/superadmin/dashboard/live/` every 30 seconds to refresh KPI numbers.

The existing template already has a `<script>` block with `completeBooking` and `cancelBooking`. We extend it.

- [ ] **Step 1: Emit `hold_expires_at` as a data attribute on each hold row**

Replace the existing pending holds table body:

```html
{% for b in pending_holds %}
<tr id="hold-{{ b.id }}"
    data-expires="{{ b.hold_expires_at.isoformat|default:'' }}">
  <td><code>{{ b.booking_reference }}</code></td>
  <td>{{ b.user.full_name }}</td>
  <td>{{ b.room.name }}</td>
  <td>{{ b.room.property.name }}</td>
  <td>{{ b.check_in }}</td>
  <td class="hold-timer" style="font-variant-numeric:tabular-nums;font-weight:600;">
    {{ b.hold_expires_at|default:"—" }}
  </td>
  <td>
    <button class="sa-btn sa-btn-sm sa-btn-danger"
            onclick="cancelBooking('{{ b.id }}', 'hold')">Cancel hold</button>
  </td>
</tr>
{% empty %}
<tr id="holds-empty-row">
  <td colspan="7" style="color:#64748b;padding:16px 12px;">No pending holds.</td>
</tr>
{% endfor %}
```

- [ ] **Step 2: Replace the `<script>` block with the full JS (countdown + polling)**

Replace the existing `<script>…</script>` block at the bottom of `dashboard.html` with:

```html
<script>
const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

// ── Hold countdown timers ────────────────────────────────────────────
function formatCountdown(ms) {
  if (ms <= 0) return 'Expired';
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function tickCountdowns() {
  document.querySelectorAll('tr[data-expires]').forEach(row => {
    const raw = row.dataset.expires;
    if (!raw) return;
    const cell = row.querySelector('.hold-timer');
    if (!cell) return;
    const ms = new Date(raw) - Date.now();
    cell.textContent = formatCountdown(ms);
    if (ms <= 120_000) cell.style.color = '#ef4444';       // red < 2 min
    else if (ms <= 300_000) cell.style.color = '#f59e0b';  // amber < 5 min
    else cell.style.color = '';
    if (ms <= 0) row.style.opacity = '0.4';
  });
}

setInterval(tickCountdowns, 1000);
tickCountdowns();

// ── KPI auto-refresh (every 30 s) ───────────────────────────────────
const KPI_SELECTORS = {
  active_bookings:  '[data-kpi="active_bookings"]',
  todays_checkins:  '[data-kpi="todays_checkins"]',
  todays_checkouts: '[data-kpi="todays_checkouts"]',
  today_revenue:    '[data-kpi="today_revenue"]',
};

function updateKpis(data) {
  for (const [key, sel] of Object.entries(KPI_SELECTORS)) {
    const el = document.querySelector(sel);
    if (!el) continue;
    if (key === 'today_revenue') {
      el.textContent = '₹' + Math.round(data[key]).toLocaleString('en-IN');
    } else {
      el.textContent = data[key];
    }
  }
  const ts = document.getElementById('last-refresh');
  if (ts) ts.textContent = 'Updated ' + new Date().toLocaleTimeString();
}

function refreshHoldsTable(holds) {
  const tbody = document.querySelector('#holds-tbody');
  if (!tbody) return;
  if (!holds.length) {
    tbody.innerHTML = '<tr id="holds-empty-row"><td colspan="7" style="color:#64748b;padding:16px 12px;">No pending holds.</td></tr>';
    return;
  }
  // Only add NEW rows; don't remove rows the user might be acting on
  const existing = new Set([...tbody.querySelectorAll('tr[id^="hold-"]')].map(r => r.id));
  holds.forEach(h => {
    if (existing.has('hold-' + h.id)) {
      // Update the countdown cell's data-expires attribute with fresh value
      const row = document.getElementById('hold-' + h.id);
      if (row && h.expires_at) row.dataset.expires = h.expires_at;
      return;
    }
    const emptyRow = tbody.querySelector('#holds-empty-row');
    if (emptyRow) emptyRow.remove();
    const tr = document.createElement('tr');
    tr.id = 'hold-' + h.id;
    tr.dataset.expires = h.expires_at || '';
    tr.innerHTML = `
      <td><code>${h.reference}</code></td>
      <td>${h.guest}</td>
      <td>${h.room}</td>
      <td>${h.property}</td>
      <td>${h.check_in}</td>
      <td class="hold-timer" style="font-variant-numeric:tabular-nums;font-weight:600;"></td>
      <td><button class="sa-btn sa-btn-sm sa-btn-danger"
                  onclick="cancelBooking('${h.id}','hold')">Cancel hold</button></td>`;
    tbody.appendChild(tr);
  });
}

async function pollDashboard() {
  try {
    const res = await fetch('/superadmin/dashboard/live/', {
      headers: {'X-Requested-With': 'XMLHttpRequest'},
    });
    if (!res.ok) return;
    const data = await res.json();
    updateKpis(data);
    refreshHoldsTable(data.pending_holds);
  } catch (_) {}
}

setInterval(pollDashboard, 30_000);

// ── Booking actions ──────────────────────────────────────────────────
async function completeBooking(id, prefix) {
  if (!confirm('Mark this booking as completed?')) return;
  const res = await fetch(`/superadmin/bookings/${id}/complete/`, {
    method: 'POST',
    headers: {'X-CSRFToken': csrf},
  });
  const data = await res.json();
  if (res.ok) {
    document.getElementById(prefix + '-' + id)?.remove();
    alert(data.message);
  } else {
    alert(data.error);
  }
}

async function cancelBooking(id, prefix) {
  const reason = prompt('Cancellation reason (optional):');
  if (reason === null) return;
  const fd = new FormData();
  fd.append('reason', reason);
  const res = await fetch(`/superadmin/bookings/${id}/cancel/`, {
    method: 'POST',
    headers: {'X-CSRFToken': csrf},
    body: fd,
  });
  const data = await res.json();
  if (res.ok) {
    document.getElementById(prefix + '-' + id)?.remove();
    alert(data.message);
  } else {
    alert(data.error);
  }
}
</script>
```

- [ ] **Step 3: Add `data-kpi` attributes to KPI stat elements and `id="holds-tbody"` to table body**

In the KPI strip section, update each `sa-stat-val` to carry a `data-kpi` attribute:

```html
<div class="sa-stat">
  <div class="sa-stat-val" data-kpi="active_bookings">{{ active_bookings }}</div>
  <div class="sa-stat-label">Active stays</div>
</div>
<div class="sa-stat">
  <div class="sa-stat-val" data-kpi="todays_checkins">{{ todays_checkins }}</div>
  <div class="sa-stat-label">Check-ins today</div>
</div>
<div class="sa-stat">
  <div class="sa-stat-val" data-kpi="todays_checkouts">{{ todays_checkouts }}</div>
  <div class="sa-stat-label">Check-outs today</div>
</div>
<div class="sa-stat">
  <div class="sa-stat-val">{{ pending_holds|length }}</div>
  <div class="sa-stat-label">Pending holds</div>
</div>
<div class="sa-stat">
  <div class="sa-stat-val" data-kpi="today_revenue">₹{{ today_revenue|floatformat:0 }}</div>
  <div class="sa-stat-label">Today revenue</div>
</div>
```

Add a "last refresh" indicator and `id="holds-tbody"` to the Pending Holds table:

```html
<!-- Pending holds -->
<div class="sa-card" style="margin-top:1.5rem">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.5rem;">
    <h2 class="sa-section-title" style="margin:0">Pending Holds</h2>
    <span id="last-refresh" style="font-size:11px;color:#94a3b8;"></span>
  </div>
  <table class="sa-table">
    <thead>
      <tr><th>Reference</th><th>Guest</th><th>Room</th><th>Property</th><th>Check-in</th><th>Expires</th><th>Action</th></tr>
    </thead>
    <tbody id="holds-tbody">
    ...existing rows...
    </tbody>
  </table>
</div>
```

- [ ] **Step 4: Start dev server and verify manually**

```bash
python manage.py runserver
```

Open `http://localhost:8000/superadmin/dashboard/`. Check:
- Pending holds column shows `MM:SS` countdown ticking live
- Holds < 2 min show red timer
- KPI numbers in the stat strip match the `/superadmin/dashboard/live/` JSON response
- No JS errors in browser console

- [ ] **Step 5: Commit**

```bash
git add templates/superadmin/dashboard.html
git commit -m "feat(superadmin): live hold countdown + 30s KPI polling on dashboard"
```

---

## Task 4: Employee Admin Dashboard — Hold Countdown + KPI Auto-Refresh

**Files:**
- Modify: `templates/employeeadmin/dashboard.html`

Mirror of Task 3 for the employee portal. Employees don't see holds (no pending_holds in their dashboard view), but they do need live KPI ticks for active stays, check-ins, check-outs.

- [ ] **Step 1: Add `data-kpi` attributes to employee KPI stat elements**

Replace the existing stat strip:

```html
<div class="ea-stats">
  <div class="ea-stat">
    <div class="ea-stat-val" data-kpi="active_bookings">{{ active_bookings }}</div>
    <div class="ea-stat-label">Active stays</div>
  </div>
  <div class="ea-stat">
    <div class="ea-stat-val" data-kpi="todays_checkins">{{ upcoming_checkins|length }}</div>
    <div class="ea-stat-label">Check-ins today</div>
  </div>
  <div class="ea-stat">
    <div class="ea-stat-val" data-kpi="todays_checkouts">{{ upcoming_checkouts|length }}</div>
    <div class="ea-stat-label">Check-outs today</div>
  </div>
</div>
```

- [ ] **Step 2: Replace the existing `<script>` block**

Replace the existing `<script>…</script>` at the bottom of `employeeadmin/dashboard.html`:

```html
<script>
const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

// ── KPI auto-refresh (every 30 s) ───────────────────────────────────
async function pollDashboard() {
  try {
    const res = await fetch('/admin-portal/dashboard/live/', {
      headers: {'X-Requested-With': 'XMLHttpRequest'},
    });
    if (!res.ok) return;
    const data = await res.json();
    ['active_bookings', 'todays_checkins', 'todays_checkouts'].forEach(key => {
      const el = document.querySelector(`[data-kpi="${key}"]`);
      if (el) el.textContent = data[key];
    });
  } catch (_) {}
}

setInterval(pollDashboard, 30_000);

// ── Booking action ───────────────────────────────────────────────────
async function completeBooking(id, prefix) {
  if (!confirm('Mark this booking as completed?')) return;
  const res = await fetch(`/admin-portal/bookings/${id}/complete/`, {
    method: 'POST',
    headers: {'X-CSRFToken': csrf},
  });
  const data = await res.json();
  if (res.ok) {
    document.getElementById(prefix + '-' + id)?.remove();
    alert(data.message);
  } else {
    alert(data.error);
  }
}
</script>
```

- [ ] **Step 3: Manual verification**

```bash
python manage.py runserver
```

Open `http://localhost:8000/admin-portal/dashboard/`. Check:
- KPI numbers match the JSON at `/admin-portal/dashboard/live/`
- No JS errors in console

- [ ] **Step 4: Commit**

```bash
git add templates/employeeadmin/dashboard.html
git commit -m "feat(employeeadmin): 30s KPI polling on employee dashboard"
```

---

## Task 5: Superadmin — Room Status Board

**Files:**
- Modify: `superadmin/views.py`
- Modify: `superadmin/urls.py`
- Create: `templates/superadmin/room_status_board.html`
- Modify: `superadmin/tests.py`

A colour-coded grid of all rooms across all properties. Each card shows room name, property, current operational status, and a dropdown to change status inline. The grid auto-refreshes every 60 seconds.

- [ ] **Step 1: Write the failing test**

```python
# superadmin/tests.py — add to file
class RoomStatusBoardTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        User = get_user_model()
        self.admin = User.objects.create_user(
            email='sa2@test.com', full_name='SA2', phone='2222222222',
            password='pass',
        )
        UserProfile.objects.filter(user=self.admin).update(role='super_admin')
        self.client = Client()
        self.client.force_login(self.admin)

    def test_status_board_renders(self):
        res = self.client.get(reverse('superadmin:room-status-board'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'status-board')

    def test_status_board_json_returns_rooms(self):
        prop = Property.objects.create(
            name='Test Prop', city='Chennai', address='1 Main', is_active=True,
        )
        Room.objects.create(
            property=prop, name='R1', city='Chennai', room_type='single',
            price_per_night=1000, capacity=2, operational_status='available',
        )
        res = self.client.get(reverse('superadmin:room-status-board-data'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('rooms', data)
        self.assertEqual(len(data['rooms']), 1)
        self.assertEqual(data['rooms'][0]['status'], 'available')
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test superadmin.tests.RoomStatusBoardTest -v 2
```

Expected: FAIL — `NoReverseMatch`.

- [ ] **Step 3: Add views to `superadmin/views.py`**

Add at the end of the file (after existing room views):

```python
# ── Room Status Board ──────────────────────────────────────────────────────────

@require_super_admin
def room_status_board(request):
    properties = Property.objects.filter(is_active=True).prefetch_related('room_set')
    return render(request, 'superadmin/room_status_board.html', {
        'properties': properties,
        'status_choices': Room.OPERATIONAL_STATUS_CHOICES,
    })


@require_super_admin
def room_status_board_data(request):
    rooms = Room.objects.select_related('property').order_by(
        'property__name', 'name'
    )
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
```

- [ ] **Step 4: Add URLs to `superadmin/urls.py`**

```python
path('rooms/status-board/', views.room_status_board, name='room-status-board'),
path('rooms/status-board/data/', views.room_status_board_data, name='room-status-board-data'),
```

Place these before the existing `rooms/create/` path so the literal path is matched first.

- [ ] **Step 5: Create `templates/superadmin/room_status_board.html`**

```html
{% extends "superadmin/base.html" %}
{% block title %}Room Status Board{% endblock %}
{% block content %}
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">
  <h1 class="sa-page-title" style="margin:0;">Room Status Board</h1>
  <span id="board-refresh-ts" style="font-size:11px;color:#94a3b8;"></span>
</div>

<div id="status-board" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;">
  {% for prop in properties %}
    {% for room in prop.room_set.all %}
    <div class="sa-card room-card" id="rc-{{ room.id }}"
         data-room-id="{{ room.id }}"
         data-status="{{ room.operational_status }}"
         style="padding:1rem;position:relative;">
      <div style="font-weight:600;font-size:13px;margin-bottom:4px;">{{ room.name }}</div>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:10px;">{{ prop.name }}</div>
      <div class="status-badge" style="margin-bottom:10px;">
        <span class="sa-badge sa-badge-{{ room.operational_status }}">{{ room.get_operational_status_display }}</span>
      </div>
      <select class="status-select"
              onchange="updateRoomStatus('{{ room.id }}', this.value, this)"
              style="width:100%;padding:4px 6px;font-size:12px;border-radius:4px;border:1px solid #334155;background:#1e293b;color:#f1f5f9;cursor:pointer;">
        {% for val, label in status_choices %}
        <option value="{{ val }}" {% if room.operational_status == val %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
      {% if not room.is_active %}
      <div style="position:absolute;inset:0;background:rgba(0,0,0,.5);border-radius:inherit;display:flex;align-items:center;justify-content:center;font-size:11px;color:#94a3b8;">Inactive</div>
      {% endif %}
    </div>
    {% endfor %}
  {% endfor %}
</div>

<script>
const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

const STATUS_COLORS = {
  available:    '#22c55e',
  maintenance:  '#f59e0b',
  cleaning:     '#3b82f6',
  out_of_order: '#ef4444',
};

async function updateRoomStatus(roomId, newStatus, selectEl) {
  const fd = new FormData();
  fd.append('operational_status', newStatus);
  const res = await fetch(`/superadmin/rooms/${roomId}/update/`, {
    method: 'POST',
    headers: {'X-CSRFToken': csrf},
    body: fd,
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || 'Update failed');
    return;
  }
  const card = document.getElementById('rc-' + roomId);
  if (card) {
    card.dataset.status = newStatus;
    const badge = card.querySelector('.status-badge');
    if (badge) badge.innerHTML = `<span class="sa-badge" style="background:${STATUS_COLORS[newStatus] || '#64748b'}20;color:${STATUS_COLORS[newStatus] || '#64748b'};border:1px solid ${STATUS_COLORS[newStatus] || '#64748b'}40;">${newStatus.replace(/_/g,' ')}</span>`;
  }
}

async function refreshBoard() {
  try {
    const res = await fetch('/superadmin/rooms/status-board/data/', {
      headers: {'X-Requested-With': 'XMLHttpRequest'},
    });
    if (!res.ok) return;
    const data = await res.json();
    data.rooms.forEach(r => {
      const card = document.getElementById('rc-' + r.id);
      if (!card || card.dataset.status === r.status) return;
      // Another user changed status — sync
      card.dataset.status = r.status;
      const sel = card.querySelector('.status-select');
      if (sel) sel.value = r.status;
    });
    const ts = document.getElementById('board-refresh-ts');
    if (ts) ts.textContent = 'Synced ' + new Date().toLocaleTimeString();
  } catch (_) {}
}

setInterval(refreshBoard, 60_000);
</script>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python manage.py test superadmin.tests.RoomStatusBoardTest -v 2
```

Expected: 2 PASS.

- [ ] **Step 7: Add nav link in `templates/superadmin/base.html`**

Find the navigation links section in `base.html` and add:

```html
<a href="{% url 'superadmin:room-status-board' %}" class="sa-nav-link {% if request.resolver_match.url_name == 'room-status-board' %}active{% endif %}">Status Board</a>
```

Place it after the existing Rooms nav link.

- [ ] **Step 8: Manual verification**

```bash
python manage.py runserver
```

Open `http://localhost:8000/superadmin/rooms/status-board/`. Check:
- Room cards render with correct status
- Changing the dropdown updates the badge in-place (no page reload)
- "Synced HH:MM:SS" timestamp appears after 60 seconds

- [ ] **Step 9: Commit**

```bash
git add superadmin/views.py superadmin/urls.py templates/superadmin/room_status_board.html templates/superadmin/base.html superadmin/tests.py
git commit -m "feat(superadmin): room status board with inline status updates + 60s sync"
```

---

## Task 6: Employee Admin — Room Status Board (Property-Scoped)

**Files:**
- Modify: `employeeadmin/views.py`
- Modify: `employeeadmin/urls.py`
- Create: `templates/employeeadmin/room_status_board.html`
- Modify: `employeeadmin/tests.py`

Mirror of Task 5, but rooms are scoped to the employee's assigned properties. Uses the existing `room_status_update` endpoint at `/admin-portal/rooms/<id>/status/`.

- [ ] **Step 1: Write the failing test**

```python
# employeeadmin/tests.py — add to file
class EmployeeRoomStatusBoardTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from accounts.models import UserProfile
        User = get_user_model()
        self.emp = User.objects.create_user(
            email='emp2@test.com', full_name='Emp2', phone='3333333333',
            password='pass',
        )
        UserProfile.objects.filter(user=self.emp).update(role='employee')
        self.client = Client()
        self.client.force_login(self.emp)

    def test_status_board_renders(self):
        res = self.client.get(reverse('employeeadmin:room-status-board'))
        self.assertEqual(res.status_code, 200)

    def test_employee_sees_only_assigned_rooms_in_board_data(self):
        """Employee with no assigned properties gets empty room list."""
        res = self.client.get(reverse('employeeadmin:room-status-board-data'))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['rooms'], [])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test employeeadmin.tests.EmployeeRoomStatusBoardTest -v 2
```

Expected: FAIL — `NoReverseMatch`.

- [ ] **Step 3: Add views to `employeeadmin/views.py`**

Add at the end of the file:

```python
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
```

- [ ] **Step 4: Add URLs to `employeeadmin/urls.py`**

```python
path('rooms/status-board/', views.room_status_board, name='room-status-board'),
path('rooms/status-board/data/', views.room_status_board_data, name='room-status-board-data'),
```

Place before the existing `rooms/create/` path.

- [ ] **Step 5: Create `templates/employeeadmin/room_status_board.html`**

```html
{% extends "employeeadmin/base.html" %}
{% block title %}Room Status Board{% endblock %}
{% block content %}
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem;">
  <h1 class="ea-page-title" style="margin:0;">Room Status Board</h1>
  <span id="board-refresh-ts" style="font-size:11px;color:#5eead4;opacity:.6;"></span>
</div>

<div id="status-board"
     style="display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:1rem;">
  {% for room in rooms %}
  <div class="ea-card room-card" id="rc-{{ room.id }}"
       data-status="{{ room.operational_status }}"
       style="padding:1rem;position:relative;">
    <div style="font-weight:600;font-size:13px;margin-bottom:3px;color:#f0fdfa;">{{ room.name }}</div>
    <div style="font-size:11px;color:#5eead4;margin-bottom:10px;">{{ room.property.name }}</div>
    <div class="status-badge" style="margin-bottom:10px;">
      <span class="ea-badge ea-badge-{{ room.operational_status }}">{{ room.get_operational_status_display }}</span>
    </div>
    <select class="status-select"
            onchange="updateRoomStatus('{{ room.id }}', this.value, this)"
            style="width:100%;padding:4px 6px;font-size:12px;border-radius:4px;border:1px solid #0d9488;background:#134e4a;color:#f0fdfa;cursor:pointer;">
      {% for val, label in status_choices %}
      <option value="{{ val }}" {% if room.operational_status == val %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    {% if not room.is_active %}
    <div style="position:absolute;inset:0;background:rgba(0,0,0,.5);border-radius:inherit;display:flex;align-items:center;justify-content:center;font-size:11px;color:#5eead4;">Inactive</div>
    {% endif %}
  </div>
  {% empty %}
  <p style="color:#5eead4;opacity:.7;grid-column:1/-1;">No rooms assigned to your properties.</p>
  {% endfor %}
</div>

<script>
const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

async function updateRoomStatus(roomId, newStatus, selectEl) {
  const fd = new FormData();
  fd.append('operational_status', newStatus);
  const res = await fetch(`/admin-portal/rooms/${roomId}/status/`, {
    method: 'POST',
    headers: {'X-CSRFToken': csrf},
    body: fd,
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || 'Update failed');
    selectEl.value = document.getElementById('rc-' + roomId).dataset.status;
    return;
  }
  const card = document.getElementById('rc-' + roomId);
  if (card) card.dataset.status = newStatus;
}

async function refreshBoard() {
  try {
    const res = await fetch('/admin-portal/rooms/status-board/data/', {
      headers: {'X-Requested-With': 'XMLHttpRequest'},
    });
    if (!res.ok) return;
    const { rooms } = await res.json();
    rooms.forEach(r => {
      const card = document.getElementById('rc-' + r.id);
      if (!card || card.dataset.status === r.status) return;
      card.dataset.status = r.status;
      const sel = card.querySelector('.status-select');
      if (sel) sel.value = r.status;
    });
    const ts = document.getElementById('board-refresh-ts');
    if (ts) ts.textContent = 'Synced ' + new Date().toLocaleTimeString();
  } catch (_) {}
}

setInterval(refreshBoard, 60_000);
</script>
{% endblock %}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python manage.py test employeeadmin.tests.EmployeeRoomStatusBoardTest -v 2
```

Expected: 2 PASS.

- [ ] **Step 7: Add nav link in `templates/employeeadmin/base.html`**

Find the nav links block and add:

```html
<a href="{% url 'employeeadmin:room-status-board' %}" class="ea-nav-link {% if request.resolver_match.url_name == 'room-status-board' %}active{% endif %}">Status Board</a>
```

Place after the existing Rooms nav link.

- [ ] **Step 8: Manual verification**

```bash
python manage.py runserver
```

Open `http://localhost:8000/admin-portal/rooms/status-board/`. Check:
- Only rooms from assigned properties appear
- Selecting a different status from dropdown saves it (POST to `/admin-portal/rooms/<id>/status/`)
- Employee with no assigned properties sees the empty state message

- [ ] **Step 9: Commit**

```bash
git add employeeadmin/views.py employeeadmin/urls.py templates/employeeadmin/room_status_board.html templates/employeeadmin/base.html employeeadmin/tests.py
git commit -m "feat(employeeadmin): room status board scoped to assigned properties"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Covered by |
|-------------|-----------|
| Live hold countdown timers | Task 3 — JS countdown from `hold_expires_at`, colour urgency thresholds |
| Dashboard KPI auto-refresh (superadmin) | Tasks 1 + 3 — JSON endpoint + 30s poll loop |
| Dashboard KPI auto-refresh (employee) | Tasks 2 + 4 — JSON endpoint + 30s poll loop |
| Room status board (superadmin) | Task 5 — all rooms, inline update, 60s sync |
| Room status board (employee) | Task 6 — assigned-property-scoped, 60s sync |

**Placeholder scan:** No TBD, TODO, or vague steps found. All code blocks are complete.

**Type consistency:**
- `dashboard_live_data` returns `pending_holds` list with `expires_at` key. Task 3 JS reads `h.expires_at`. ✓
- `room_status_board_data` returns `rooms[].status`. Task 5/6 JS reads `r.status`. ✓
- `room_status_update` endpoint (existing, Task 6) accepts `operational_status` in POST body. Task 6 JS sends `fd.append('operational_status', newStatus)`. ✓
- Superadmin room update endpoint (Task 5) uses `room_update` view — the existing `room_update` POST handler in `superadmin/views.py` must accept `operational_status` as a form field. Verify this before running Task 5 Step 8.
