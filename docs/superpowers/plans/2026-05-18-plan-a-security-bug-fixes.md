# Plan A — Security & Bug Fixes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four real bugs that block safe operation of the admin portals: room status enum mismatch, employee-rooms security fallback, employee dashboard scope leak, and missing audit-log action codes.

**Architecture:** Surgical fixes only. Each task is one file group + tests + commit. Nothing here is feature work — this is the foundation Plan B and Plan C build on.

**Tech Stack:** Django 6, Django ORM, Django test framework.

---

## Why each fix matters (real-world use case)

| Bug | Real symptom |
|-----|-------------|
| Room status mismatch | Housekeeper marks a room "Cleaning" from the employee portal → 400 error, room never reflects status, guest is checked into a dirty room |
| `_assigned_rooms()` fallback | A new employee with **no** assigned properties can view, block, and re-rate **every** room on the platform |
| Employee dashboard scope | Pondicherry front-desk sees Bengaluru's check-ins/outs — confusing and a PII leak in fin_level='C' redaction edge cases |
| Missing audit actions | Booking cancellations and room-status changes happen with no trace — super admin cannot answer "who cancelled this?" |

---

## Task 1: Fix Room operational status enum

**Files:**
- Modify: `rooms/models.py` — `Room.OPERATIONAL_STATUS_CHOICES`
- Create: `rooms/migrations/00XX_room_operational_status_expand.py`
- Create: `rooms/tests.py` (if missing) — append test

- [ ] **Step 1: Find current choices in `rooms/models.py`**

Search for `OPERATIONAL_STATUS_CHOICES` in `rooms/models.py`. It currently reads:

```python
OPERATIONAL_STATUS_CHOICES = [
    ('available', 'Available'),
    ('needs_cleaning', 'Needs Cleaning'),
    ('maintenance', 'Maintenance'),
]
```

- [ ] **Step 2: Replace with the four canonical hotel statuses**

```python
OPERATIONAL_STATUS_CHOICES = [
    ('available', 'Available'),
    ('cleaning', 'Cleaning'),
    ('maintenance', 'Maintenance'),
    ('out_of_order', 'Out of Order'),
]
```

- [ ] **Step 3: Generate the migration**

```bash
cd /Users/sukheshkannasaravanan/Documents/GitHub/TTR-V2
python manage.py makemigrations rooms --name room_operational_status_expand
```

Expected output: a new file `rooms/migrations/00XX_room_operational_status_expand.py` listing `AlterField` on `Room.operational_status`.

- [ ] **Step 4: Backfill existing `needs_cleaning` rows to `cleaning` in the same migration**

Open the generated migration and append a data-migration operation. The file should look like:

```python
from django.db import migrations, models


def rename_needs_cleaning(apps, schema_editor):
    Room = apps.get_model('rooms', 'Room')
    Room.objects.filter(operational_status='needs_cleaning').update(operational_status='cleaning')


def rename_cleaning_back(apps, schema_editor):
    Room = apps.get_model('rooms', 'Room')
    Room.objects.filter(operational_status='cleaning').update(operational_status='needs_cleaning')


class Migration(migrations.Migration):

    dependencies = [
        ('rooms', 'XXXX_previous_migration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='room',
            name='operational_status',
            field=models.CharField(
                choices=[
                    ('available', 'Available'),
                    ('cleaning', 'Cleaning'),
                    ('maintenance', 'Maintenance'),
                    ('out_of_order', 'Out of Order'),
                ],
                default='available',
                max_length=20,
            ),
        ),
        migrations.RunPython(rename_needs_cleaning, rename_cleaning_back),
    ]
```

Keep the `dependencies` line that `makemigrations` generated — don't replace it.

- [ ] **Step 5: Apply the migration**

```bash
python manage.py migrate rooms
```

Expected: `Applying rooms.00XX_room_operational_status_expand... OK`

- [ ] **Step 6: Write a regression test in `rooms/tests.py`**

If `rooms/tests.py` doesn't exist, create it. Append:

```python
from django.test import TestCase
from rooms.models import Room, Property


class RoomOperationalStatusTest(TestCase):
    def setUp(self):
        self.prop = Property.objects.create(name='Test Prop', city='Pondy', is_active=True)
        self.room = Room.objects.create(
            property=self.prop,
            name='R1',
            city='Pondy',
            room_type='single',
            price_per_night=2000,
            capacity=2,
        )

    def test_default_status_is_available(self):
        self.assertEqual(self.room.operational_status, 'available')

    def test_all_four_statuses_accept(self):
        for status in ['available', 'cleaning', 'maintenance', 'out_of_order']:
            self.room.operational_status = status
            self.room.full_clean()
            self.room.save()
            self.assertEqual(Room.objects.get(pk=self.room.pk).operational_status, status)
```

- [ ] **Step 7: Run the test**

```bash
python manage.py test rooms.tests.RoomOperationalStatusTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 2 PASS.

- [ ] **Step 8: Commit**

```bash
git add rooms/models.py rooms/migrations/ rooms/tests.py
git commit -m "fix: expand Room.operational_status to {available, cleaning, maintenance, out_of_order} with backfill"
```

---

## Task 2: Fix `_assigned_rooms()` security fallback

**Files:**
- Modify: `employeeadmin/views.py` lines 18–26 (`_assigned_rooms` helper)
- Create/Append: `employeeadmin/tests.py`

- [ ] **Step 1: Replace the helper in `employeeadmin/views.py`**

Current code:
```python
def _assigned_rooms(request):
    """Rooms belonging to properties assigned to this employee."""
    try:
        props = request.user.userprofile.assigned_properties.values_list('id', flat=True)
        if props:
            return Room.objects.filter(property_id__in=props)
    except Exception:
        pass
    return Room.objects.all()
```

Replace with:
```python
def _assigned_rooms(request):
    """Rooms belonging to properties assigned to this employee.

    Security: an employee with no assigned properties sees NO rooms,
    not all rooms. This prevents privilege escalation when a super
    admin forgets to assign properties on employee creation.
    """
    try:
        props = list(request.user.userprofile.assigned_properties.values_list('id', flat=True))
    except Exception:
        return Room.objects.none()
    if not props:
        return Room.objects.none()
    return Room.objects.filter(property_id__in=props)
```

- [ ] **Step 2: Write tests in `employeeadmin/tests.py`**

If the file doesn't exist, create it. Add:

```python
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model

from rooms.models import Room, Property
from employeeadmin.views import _assigned_rooms

User = get_user_model()


class AssignedRoomsSecurityTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.prop_a = Property.objects.create(name='Prop A', city='Pondy', is_active=True)
        self.prop_b = Property.objects.create(name='Prop B', city='Bengaluru', is_active=True)
        Room.objects.create(property=self.prop_a, name='A1', city='Pondy',
                            room_type='single', price_per_night=1000, capacity=2)
        Room.objects.create(property=self.prop_b, name='B1', city='Bengaluru',
                            room_type='single', price_per_night=1000, capacity=2)

        self.user = User.objects.create_user(
            email='emp@example.com', password='x', is_active=True,
        )
        self.user.userprofile.role = 'employee_admin'
        self.user.userprofile.save()

    def _req(self):
        req = self.factory.get('/')
        req.user = self.user
        return req

    def test_employee_with_no_properties_sees_no_rooms(self):
        self.assertEqual(_assigned_rooms(self._req()).count(), 0)

    def test_employee_sees_only_assigned_property_rooms(self):
        self.user.userprofile.assigned_properties.add(self.prop_a)
        rooms = _assigned_rooms(self._req())
        self.assertEqual(rooms.count(), 1)
        self.assertEqual(rooms.first().property_id, self.prop_a.id)

    def test_anonymous_or_broken_profile_sees_no_rooms(self):
        broken_user = User.objects.create_user(email='x@x.com', password='x', is_active=True)
        broken_user.userprofile.delete()
        req = self.factory.get('/')
        req.user = broken_user
        self.assertEqual(_assigned_rooms(req).count(), 0)
```

- [ ] **Step 3: Run the tests**

```bash
python manage.py test employeeadmin.tests.AssignedRoomsSecurityTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 3 PASS.

- [ ] **Step 4: Commit**

```bash
git add employeeadmin/views.py employeeadmin/tests.py
git commit -m "fix(security): _assigned_rooms returns empty queryset for unassigned employees"
```

---

## Task 3: Scope employeeadmin dashboard and bookings to assigned properties

**Files:**
- Modify: `employeeadmin/views.py` — `dashboard()` and `bookings_list()`
- Append: `employeeadmin/tests.py`

- [ ] **Step 1: Update `dashboard()` to scope by assigned rooms**

Replace the body of `dashboard()` in `employeeadmin/views.py`:

```python
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
```

- [ ] **Step 2: Update `bookings_list()` to scope by assigned rooms**

Replace `bookings_list()` body:

```python
@require_employee
def bookings_list(request):
    fin = _fin_level(request)
    rooms = _assigned_rooms(request)
    bookings = Booking.objects.filter(
        room__in=rooms,
        status__in=('confirmed', 'completed', 'cancelled'),
    ).select_related('user', 'room', 'room__property').order_by('-check_in')[:50]
    return render(request, 'employeeadmin/bookings.html', {'bookings': bookings, 'fin': fin})
```

- [ ] **Step 3: Append test in `employeeadmin/tests.py`**

```python
import datetime
from django.urls import reverse
from rooms.models import Booking


class EmployeeScopeTest(TestCase):
    def setUp(self):
        self.prop_a = Property.objects.create(name='Prop A', city='Pondy', is_active=True)
        self.prop_b = Property.objects.create(name='Prop B', city='Bengaluru', is_active=True)
        self.room_a = Room.objects.create(property=self.prop_a, name='A1', city='Pondy',
                                          room_type='single', price_per_night=1000, capacity=2)
        self.room_b = Room.objects.create(property=self.prop_b, name='B1', city='Bengaluru',
                                          room_type='single', price_per_night=1000, capacity=2)

        self.guest = User.objects.create_user(email='g@x.com', password='x', is_active=True)
        today = datetime.date.today()
        Booking.objects.create(room=self.room_a, user=self.guest, check_in=today,
                               check_out=today + datetime.timedelta(days=2),
                               guests=1, status='confirmed', total_price=2000)
        Booking.objects.create(room=self.room_b, user=self.guest, check_in=today,
                               check_out=today + datetime.timedelta(days=2),
                               guests=1, status='confirmed', total_price=2000)

        self.emp = User.objects.create_user(email='e@x.com', password='x', is_active=True)
        self.emp.userprofile.role = 'employee_admin'
        self.emp.userprofile.assigned_properties.add(self.prop_a)
        self.emp.userprofile.save()

    def test_dashboard_only_shows_assigned_property_bookings(self):
        self.client.force_login(self.emp)
        res = self.client.get(reverse('employeeadmin:dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['active_bookings'], 1)

    def test_bookings_list_only_shows_assigned_property_bookings(self):
        self.client.force_login(self.emp)
        res = self.client.get(reverse('employeeadmin:bookings'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.context['bookings']), 1)
        self.assertEqual(res.context['bookings'][0].room.property_id, self.prop_a.id)
```

- [ ] **Step 4: Run the new tests**

```bash
python manage.py test employeeadmin.tests.EmployeeScopeTest --settings=hotel_booking.settings.dev -v 2
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add employeeadmin/views.py employeeadmin/tests.py
git commit -m "fix(security): scope employee dashboard and bookings to assigned properties"
```

---

## Task 4: Add missing audit-log action codes

**Files:**
- Modify: `superadmin/models.py` — `AuditLog.ACTION_CHOICES`
- Create: `superadmin/migrations/00XX_auditlog_action_choices.py`

- [ ] **Step 1: Extend `ACTION_CHOICES` in `superadmin/models.py`**

Find the `AuditLog` class. Locate `ACTION_CHOICES`. Append three new entries — the final list should read:

```python
ACTION_CHOICES = [
    ('EMPLOYEE_CREATED', 'Employee Created'),
    ('EMPLOYEE_UPDATED', 'Employee Updated'),
    ('EMPLOYEE_LOCKED', 'Employee Locked'),
    ('EMPLOYEE_UNLOCKED', 'Employee Unlocked'),
    ('PASSWORD_RESET', 'Password Reset'),
    ('BOOKING_CANCELLED', 'Booking Cancelled'),
    ('BOOKING_COMPLETED', 'Booking Completed'),
    ('ROOM_UPDATED', 'Room Updated'),
    ('ROOM_STATUS_UPDATED', 'Room Status Updated'),
    ('TAX_CONFIG_UPDATED', 'Tax Config Updated'),
    ('LOYALTY_CONFIG_UPDATED', 'Loyalty Config Updated'),
    ('LOYALTY_POINTS_ADJUSTED', 'Loyalty Points Adjusted'),
    ('PROPERTY_ASSIGNMENT_CHANGED', 'Property Assignment Changed'),
]
```

- [ ] **Step 2: Generate the migration**

```bash
python manage.py makemigrations superadmin --name auditlog_action_choices
```

Expected: a new migration containing one `AlterField` on `AuditLog.action`.

- [ ] **Step 3: Apply the migration**

```bash
python manage.py migrate superadmin
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add superadmin/models.py superadmin/migrations/
git commit -m "feat: add BOOKING_COMPLETED, ROOM_STATUS_UPDATED, LOYALTY_POINTS_ADJUSTED, PROPERTY_ASSIGNMENT_CHANGED audit actions"
```

---

## Final Verification

- [ ] **Run the full test suite**

```bash
python manage.py test --settings=hotel_booking.settings.dev -v 2
```

Expected: all tests pass, no migrations pending (`python manage.py makemigrations --dry-run` shows "No changes detected").
