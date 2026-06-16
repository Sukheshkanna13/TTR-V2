# Featured Stays Carousel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the home page "Featured stays" carousel DB-driven, controllable via a star toggle in both admin panels, with a guaranteed-3 fallback and a mobile "View more".

**Architecture:** Add an `is_featured` flag to `Room`; put the selection rule (featured-first, then highest-rated fallback, min 3, image-gated) in a `Room` manager method; render real `Room` objects in the carousel; extend the existing `action`-POST room views in both admin panels with a `toggle_featured` branch and a ★ button.

**Tech Stack:** Django 6 (MVT, SSR templates), SQLite (dev), Django `TestCase` test runner (`python manage.py test`, settings default to `hotel_booking.settings.dev`).

**Reference spec:** `docs/superpowers/specs/2026-06-16-featured-stays-carousel-design.md`

---

## File Structure

- `rooms/models.py` — add `is_featured` field + `RoomManager.featured_for_home()` (selection logic, single source of truth).
- `rooms/migrations/0xxx_room_is_featured.py` — generated migration.
- `rooms/tests.py` — unit tests for `featured_for_home()`.
- `core/views.py` — `home_page` calls the manager instead of the hardcoded list.
- `templates/pages/index.html` — carousel loop renders `Room` objects; mobile "View more" button + JS.
- `static/style.css` — mobile view-more CSS.
- `employeeadmin/views.py` + `templates/employeeadmin/rooms.html` — `toggle_featured` action + ★ button.
- `superadmin/views.py` + `templates/superadmin/rooms.html` — `toggle_featured` action + ★ button.
- `employeeadmin/tests.py`, `superadmin/tests.py` — toggle tests.

---

## Task 1: Add `is_featured` field to Room + migration

**Files:**
- Modify: `rooms/models.py` (Room model, after `operational_status` field ~line 135)

- [ ] **Step 1: Add the field**

In `rooms/models.py`, inside `class Room`, immediately after the `operational_status` field definition (before `created_at`), add:

```python
    is_featured = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Show this room in the Featured Stays carousel on the home page.",
    )
```

- [ ] **Step 2: Generate the migration**

Run: `python manage.py makemigrations rooms`
Expected: creates `rooms/migrations/0XXX_room_is_featured.py` with one `AddField` for `is_featured`.

- [ ] **Step 3: Apply the migration**

Run: `python manage.py migrate rooms`
Expected: `Applying rooms.0XXX_room_is_featured... OK`

- [ ] **Step 4: Commit**

```bash
git add rooms/models.py rooms/migrations/
git commit -m "feat(rooms): add is_featured flag to Room"
```

---

## Task 2: `featured_for_home()` selection logic (TDD)

**Files:**
- Test: `rooms/tests.py` (append new test class)
- Modify: `rooms/models.py` (add `RoomManager` above `class Room`; set `objects = RoomManager()`)

- [ ] **Step 1: Write the failing tests**

Append to `rooms/tests.py`. (The file already imports `Room`, `Property`; add `RoomImage` to the existing `from rooms.models import ...` line, and `Decimal` is already imported.)

```python
from rooms.models import RoomImage  # add to existing rooms.models import if not present


def _frprop(name, rating='4.5'):
    return Property.objects.create(
        name=name, city='Pondy', address='addr', is_active=True, rating=rating,
    )


def _frroom(prop, name='R', featured=False, active=True,
            status='available', with_image=True):
    room = Room.objects.create(
        property=prop, name=name, city='Pondy', room_type='single',
        price_per_night=Decimal('2000'), capacity=2,
        operational_status=status, is_active=active, is_featured=featured,
    )
    if with_image:
        RoomImage.objects.create(room=room, image='room_images/x.jpg')
    return room


class FeaturedForHomeTest(TestCase):
    def test_no_featured_returns_three_highest_rated(self):
        a = _frroom(_frprop('A', '4.9'), name='A')
        b = _frroom(_frprop('B', '4.8'), name='B')
        c = _frroom(_frprop('C', '4.7'), name='C')
        _frroom(_frprop('D', '4.6'), name='D')
        result = Room.objects.featured_for_home()
        self.assertEqual([r.id for r in result], [a.id, b.id, c.id])

    def test_fewer_than_three_featured_fills_to_three(self):
        low = _frroom(_frprop('Low', '4.0'), name='Low', featured=True)
        a = _frroom(_frprop('A', '4.9'), name='A')
        b = _frroom(_frprop('B', '4.8'), name='B')
        result = Room.objects.featured_for_home()
        self.assertEqual(result[0].id, low.id)          # featured first
        self.assertEqual({r.id for r in result}, {low.id, a.id, b.id})
        self.assertEqual(len(result), 3)

    def test_three_or_more_featured_returns_all(self):
        rooms = [_frroom(_frprop(f'P{i}', '4.5'), name=f'F{i}', featured=True)
                 for i in range(4)]
        result = Room.objects.featured_for_home()
        self.assertEqual(len(result), 4)
        self.assertEqual({r.id for r in result}, {r.id for r in rooms})

    def test_imageless_featured_room_excluded(self):
        no_img = _frroom(_frprop('NoImg', '5.0'), name='NoImg',
                         featured=True, with_image=False)
        a = _frroom(_frprop('A', '4.9'), name='A')
        b = _frroom(_frprop('B', '4.8'), name='B')
        c = _frroom(_frprop('C', '4.7'), name='C')
        result = Room.objects.featured_for_home()
        self.assertNotIn(no_img.id, [r.id for r in result])
        self.assertEqual({r.id for r in result}, {a.id, b.id, c.id})

    def test_inactive_and_unavailable_excluded(self):
        inactive = _frroom(_frprop('In', '5.0'), name='In', active=False)
        cleaning = _frroom(_frprop('Cl', '5.0'), name='Cl', status='cleaning')
        a = _frroom(_frprop('A', '4.9'), name='A')
        b = _frroom(_frprop('B', '4.8'), name='B')
        c = _frroom(_frprop('C', '4.7'), name='C')
        result_ids = [r.id for r in Room.objects.featured_for_home()]
        self.assertNotIn(inactive.id, result_ids)
        self.assertNotIn(cleaning.id, result_ids)
        self.assertEqual(set(result_ids), {a.id, b.id, c.id})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test rooms.tests.FeaturedForHomeTest -v 2`
Expected: FAIL — `AttributeError: 'Manager' object has no attribute 'featured_for_home'`.

- [ ] **Step 3: Implement the manager**

In `rooms/models.py`, add this class **immediately before** `class Room(models.Model):`:

```python
class RoomManager(models.Manager):
    """Manager for Room. Owns the home-page featured-stays selection rule."""

    def featured_for_home(self, min_count=3):
        """Return the rooms for the home carousel.

        Featured (starred) rooms first, ordered by their property's rating
        (highest first, nulls last) then newest. If fewer than ``min_count``
        are featured, fill the remaining slots with the highest-rated
        non-featured rooms. Only active, available rooms that have at least
        one image are eligible.
        """
        from django.db.models import F

        pool = list(
            self.get_queryset()
            .filter(is_active=True, operational_status=Room.STATUS_AVAILABLE)
            .filter(images__isnull=False)
            .distinct()
            .select_related("property")
            .prefetch_related("images")
            .order_by(F("property__rating").desc(nulls_last=True), "-created_at")
        )

        featured = [r for r in pool if r.is_featured]
        if len(featured) >= min_count:
            return featured

        result = list(featured)
        featured_ids = {r.id for r in featured}
        for room in pool:
            if len(result) >= min_count:
                break
            if room.id not in featured_ids:
                result.append(room)
        return result
```

Then, inside `class Room`, add the manager binding (place it right after the `id` field or just before `class Meta`):

```python
    objects = RoomManager()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test rooms.tests.FeaturedForHomeTest -v 2`
Expected: PASS (5 tests OK).

- [ ] **Step 5: Run the full rooms suite to confirm no regressions**

Run: `python manage.py test rooms -v 1`
Expected: OK (the existing `Room.objects.filter/create/...` calls still work via the custom manager).

- [ ] **Step 6: Commit**

```bash
git add rooms/models.py rooms/tests.py
git commit -m "feat(rooms): featured_for_home() selection logic with min-3 fallback"
```

---

## Task 3: Wire the home page view + carousel template

**Files:**
- Modify: `core/views.py` (`home_page`, ~lines 33-65)
- Modify: `templates/pages/index.html` (Featured Stays card loop, lines 64-96)

- [ ] **Step 1: Update the view**

In `core/views.py` `home_page`, delete the `imgs` helper (lines 33-34) and the entire `featured = [...]` block (lines 36-43). At the top of the function add `Room` to the import and build the queryset. The import line becomes:

```python
    from rooms.models import Property, Room
```

Immediately before the `return render(...)`, add:

```python
    featured_rooms = Room.objects.featured_for_home()
```

Change the context dict key `'featured': featured,` to:

```python
        'featured_rooms': featured_rooms,
```

(Leave `cities`, `hero`, `moments`, `journeys`, `tiers` untouched.)

- [ ] **Step 2: Update the carousel template**

In `templates/pages/index.html`, replace the loop body (lines 65-95, the `{% for c in featured %} ... {% endfor %}`) with:

```django
      {% for room in featured_rooms %}
      {% with p=room.property %}
      <div class="tt-card{% if forloop.counter > 3 %} tt-featured-extra{% endif %}" onclick="location.href='{% url 'rooms:room-detail-page' %}?id={{ room.id }}'">
        <div class="tt-card-media home-carousel" data-idx="0">
          <div class="tt-slider-track">
            {% for img in room.images.all %}
            <img src="{{ img.image.url }}" alt="{{ room.name }}" class="tt-slider-img" loading="lazy" draggable="false">
            {% endfor %}
          </div>
          <button type="button" class="tt-slider-btn prev" aria-label="Previous" onclick="event.stopPropagation();carPrev(this)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>
          </button>
          <button type="button" class="tt-slider-btn next" aria-label="Next" onclick="event.stopPropagation();carNext(this)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
          <div class="tt-slider-dots">
            {% for img in room.images.all %}<div class="tt-dot {% if forloop.first %}active{% endif %}"></div>{% endfor %}
          </div>
          <div class="tt-card-tags">
            <span class="tt-tag">{{ room.city }}</span>
            <span class="tt-tag tt-tag-dark">&#9733; {{ p.rating|default:"4.5" }}</span>
          </div>
        </div>
        <div class="tt-card-body">
          <div class="tt-card-row" style="align-items:center;">
            <span class="tt-card-name">{{ room.name }}</span>
            <button type="button" class="tt-btn-card-cta" onclick="event.stopPropagation();location.href='{% url 'rooms:room-detail-page' %}?id={{ room.id }}'">Book now</button>
          </div>
          <div class="tt-card-area">{{ p.address|default:p.name|default:room.city }}</div>
        </div>
      </div>
      {% endwith %}
      {% endfor %}
```

- [ ] **Step 3: Smoke-test the home page renders**

Run:
```bash
python manage.py shell -c "from django.test import Client; r=Client().get('/'); print(r.status_code)"
```
Expected: `200`. (If there are no rooms-with-images in the dev DB, the carousel renders empty — that is acceptable here; Task 3 only verifies the page does not error.)

- [ ] **Step 4: Commit**

```bash
git add core/views.py templates/pages/index.html
git commit -m "feat(home): render DB-driven featured stays from Room.featured_for_home()"
```

---

## Task 4: Mobile "View more" toggle

**Files:**
- Modify: `static/style.css` (append)
- Modify: `templates/pages/index.html` (add button after the grid; add JS near existing carousel script)

- [ ] **Step 1: Add CSS**

Append to `static/style.css`:

```css
/* ── Featured stays: mobile "View more" ─────────────────────────── */
.tt-featured-more { display: none; margin-top: 24px; }
@media (max-width: 768px) {
  .tt-featured-extra { display: none; }
  .tt-featured-extra.is-open { display: block; }
  .tt-featured-more { display: inline-flex; }
}
```

- [ ] **Step 2: Add the "View more" button**

In `templates/pages/index.html`, immediately after the `</div>` that closes `tt-grid-3` (the line after `{% endfor %}`, before the section's closing `</div></section>`), insert:

```django
    {% if featured_rooms|length > 3 %}
    <button type="button" class="tt-btn-link tt-featured-more" id="featuredMoreBtn" onclick="featuredShowMore(this)">View more stays &rarr;</button>
    {% endif %}
```

- [ ] **Step 3: Add the toggle JS**

In `templates/pages/index.html`, find the existing `<script>` block that defines `carPrev`/`carNext` and add this function inside it:

```javascript
function featuredShowMore(btn) {
  document.querySelectorAll('.tt-featured-extra').forEach(function (el) {
    el.classList.add('is-open');
  });
  btn.style.display = 'none';
}
```

- [ ] **Step 4: Verify the page still renders**

Run:
```bash
python manage.py shell -c "from django.test import Client; r=Client().get('/'); print(r.status_code)"
```
Expected: `200`.

- [ ] **Step 5: Commit**

```bash
git add static/style.css templates/pages/index.html
git commit -m "feat(home): mobile View more toggle for featured stays beyond 3"
```

---

## Task 5: Employee Admin — `toggle_featured` action + ★ button (TDD)

**Files:**
- Test: `employeeadmin/tests.py` (add methods to `EmployeeRoomCrudTest`)
- Modify: `employeeadmin/views.py` (`room_edit`, before final `return` ~line 287)
- Modify: `templates/employeeadmin/rooms.html` (actions cell ~line 101; JS ~line 219)

- [ ] **Step 1: Write the failing tests**

Add to `class EmployeeRoomCrudTest` in `employeeadmin/tests.py` (the class already has `self.room_a` in `prop_a` and `self.prop_b` unassigned; `json` is already imported):

```python
    def test_room_edit_toggle_featured(self):
        url = reverse('employeeadmin:room-edit', args=[self.room_a.id])
        res = self.client.post(url, data=json.dumps({
            'action': 'toggle_featured',
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['is_featured'])
        self.room_a.refresh_from_db()
        self.assertTrue(self.room_a.is_featured)

    def test_cannot_feature_unassigned_room(self):
        intruder = Room.objects.create(
            property=self.prop_b, name='B1', city='Bengaluru',
            room_type='single', price_per_night=1000, capacity=2,
        )
        url = reverse('employeeadmin:room-edit', args=[intruder.id])
        res = self.client.post(url, data=json.dumps({
            'action': 'toggle_featured',
        }), content_type='application/json')
        self.assertEqual(res.status_code, 403)
        intruder.refresh_from_db()
        self.assertFalse(intruder.is_featured)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test employeeadmin.tests.EmployeeRoomCrudTest -v 2`
Expected: `test_room_edit_toggle_featured` FAILS (returns 400 "Unknown action", so `res.json()['is_featured']` raises `KeyError`). `test_cannot_feature_unassigned_room` already passes (scope check returns 403 before action dispatch) — that's fine, it guards the security path.

- [ ] **Step 3: Implement the action**

In `employeeadmin/views.py`, inside `room_edit`, add this branch immediately before the final `return JsonResponse({'error': 'Unknown action.'}, status=400)`:

```python
    if action == 'toggle_featured':
        room.is_featured = not room.is_featured
        room.save(update_fields=['is_featured'])
        return JsonResponse({
            'message': f'Room {"featured" if room.is_featured else "unfeatured"}.',
            'is_featured': room.is_featured,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test employeeadmin.tests.EmployeeRoomCrudTest -v 2`
Expected: PASS.

- [ ] **Step 5: Add the ★ button to the template**

In `templates/employeeadmin/rooms.html`, in the actions `<td>` (after the `toggleActive` button, ~line 105, before the images `<a>`), add:

```django
        <button class="ea-btn ea-btn-sm" id="feat-btn-{{ r.id }}" onclick="toggleFeatured('{{ r.id }}', this)" title="Feature on home page">
          {% if r.is_featured %}★ Featured{% else %}☆ Feature{% endif %}
        </button>
```

- [ ] **Step 6: Add the toggle JS**

In `templates/employeeadmin/rooms.html`, after the `toggleActive` function (~line 219), add:

```javascript
async function toggleFeatured(roomId, btn) {
  const data = await roomAction(roomId, {action: 'toggle_featured'});
  if (data.error) { alert(data.error); return; }
  location.reload();
}
```

- [ ] **Step 7: Commit**

```bash
git add employeeadmin/views.py employeeadmin/tests.py templates/employeeadmin/rooms.html
git commit -m "feat(employeeadmin): star toggle to feature rooms on home page"
```

---

## Task 6: Super Admin — `toggle_featured` action + ★ button (TDD)

**Files:**
- Test: `superadmin/tests.py` (new test class)
- Modify: `superadmin/views.py` (`room_update`, before final `return` ~line 494)
- Modify: `templates/superadmin/rooms.html` (actions cell ~line 104; JS ~line 213)

- [ ] **Step 1: Write the failing test**

Append to `superadmin/tests.py` (add `from rooms.models import Property, Room` to the imports at the top):

```python
class SuperAdminFeatureToggleTest(TestCase):
    def setUp(self):
        self.admin, _ = _make_super_admin()
        self.client = Client()
        self.client.force_login(self.admin)
        self.prop = Property.objects.create(name='P', city='Pondy', is_active=True)
        self.room = Room.objects.create(
            property=self.prop, name='R1', city='Pondy',
            room_type='single', price_per_night=1000, capacity=2,
        )

    def test_toggle_featured_flips_flag(self):
        url = reverse('superadmin:room-update', args=[self.room.id])
        res = self.client.post(url, data=json.dumps({
            'action': 'toggle_featured',
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['is_featured'])
        self.room.refresh_from_db()
        self.assertTrue(self.room.is_featured)

    def test_toggle_featured_twice_returns_false(self):
        url = reverse('superadmin:room-update', args=[self.room.id])
        self.client.post(url, data=json.dumps({'action': 'toggle_featured'}),
                         content_type='application/json')
        res = self.client.post(url, data=json.dumps({'action': 'toggle_featured'}),
                               content_type='application/json')
        self.assertFalse(res.json()['is_featured'])
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_featured)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test superadmin.tests.SuperAdminFeatureToggleTest -v 2`
Expected: FAIL — action returns 400 "Unknown action", `res.json()['is_featured']` raises `KeyError`.

- [ ] **Step 3: Implement the action**

In `superadmin/views.py`, inside `room_update`, add this branch immediately before the final `return JsonResponse({'error': 'Unknown action.'}, status=400)`:

```python
    if action == 'toggle_featured':
        room.is_featured = not room.is_featured
        room.save(update_fields=['is_featured'])
        state = 'featured' if room.is_featured else 'unfeatured'
        _log(request, 'ROOM_UPDATED', detail=f"room={room.name}, {state}")
        return JsonResponse({
            'message': f'Room {state}.',
            'is_featured': room.is_featured,
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test superadmin.tests.SuperAdminFeatureToggleTest -v 2`
Expected: PASS.

- [ ] **Step 5: Add the ★ button to the template**

In `templates/superadmin/rooms.html`, in the actions `<td>` (after the `toggleActive` button ~line 105, before the images `<a>`), add:

```django
        <button class="sa-btn sa-btn-sm" id="feat-btn-{{ r.id }}" onclick="toggleFeatured('{{ r.id }}', this)" title="Feature on home page">
          {% if r.is_featured %}★ Featured{% else %}☆ Feature{% endif %}
        </button>
```

- [ ] **Step 6: Add the toggle JS**

In `templates/superadmin/rooms.html`, after the `toggleActive` function (~line 213), add:

```javascript
async function toggleFeatured(roomId, btn) {
  const data = await roomAction(roomId, {action: 'toggle_featured'});
  if (data.error) { alert(data.error); return; }
  location.reload();
}
```

- [ ] **Step 7: Run the full admin suites + rooms suite**

Run: `python manage.py test rooms employeeadmin superadmin -v 1`
Expected: OK, no failures.

- [ ] **Step 8: Commit**

```bash
git add superadmin/views.py superadmin/tests.py templates/superadmin/rooms.html
git commit -m "feat(superadmin): star toggle to feature rooms on home page"
```

---

## Final manual verification (after all tasks)

1. `python manage.py runserver`, log in as Super Admin → Rooms.
2. Click **☆ Feature** on a room that has images → button becomes **★ Featured**.
3. Load `/` → that room appears in the Featured Stays carousel; its card deep-links to `/rooms/room/page/?id=<room.id>`.
4. Unfeature all rooms → carousel still shows 3 highest-rated rooms (fallback).
5. Feature 4+ rooms → on a narrow viewport, only 3 show with a "View more stays" button that reveals the rest.
6. Log in as an Employee Admin → the ★ button only appears/works for rooms in assigned properties (POST to a non-assigned room returns 403).
