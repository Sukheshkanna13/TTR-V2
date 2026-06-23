# Featured Stays Carousel — DB-driven with Admin Star Control

**Date:** 2026-06-16
**Status:** Approved design — ready for implementation plan
**Apps touched:** `rooms`, `core`, `employeeadmin`, `superadmin`, `templates`

---

## Problem

The "Featured stays" carousel on the home page is **hardcoded** as a Python list of
dicts in [`core/views.py`](../../../core/views.py) (`featured = [...]`), pointing at
static image folders. It is not connected to the database, so admins cannot control
which stays appear, and the cards do not link to real rooms.

We want admins (Super Admin and Employee Admin) to control the carousel directly from
the room-edit section via a "star" (feature) toggle, with changes reflected on the home
page on the next page load.

## Goals

1. Admins can **star/unstar a Room** as "featured" from both admin panels.
2. The home page carousel is **DB-driven** — starred rooms appear on next page load.
3. **Graceful fallback:** if fewer than 3 rooms are featured (including zero), the
   carousel auto-fills from the DB so **at least 3 cards** always render.
4. **Mobile UI protection:** when more than 3 cards exist, mobile shows the first 3 with
   a "View more" toggle; desktop shows all (grid wraps).

## Non-Goals (YAGNI)

- No WebSockets / live push (confirmed: simple flow). Reflected on next page load.
- No drag-to-reorder of featured rooms. Order is rating-driven and deterministic.
- No per-card free-text sub-locality copy (e.g. "100m from beach"). Use existing fields.
- No change to the `Property` model.

---

## Decisions (resolved during brainstorming)

| Question | Decision |
|----------|----------|
| Featured entity | **Room** (star toggle lives on each room in the admin room-edit panel). |
| "Real-time" meaning | **DB-driven, reflected on next page load.** No polling/WebSockets. |
| Fallback fill | **Highest-rated active rooms** (by `property.rating` desc, then `-created_at`). |
| Overflow / mobile | **Desktop shows all featured; mobile shows 3 + "View more"** inline toggle. |
| Imageless starred room | **Excluded** from the carousel (would break the card UI). |
| Card click target | **Deep-link to the real room detail page**: `rooms:room-detail-page?id=<room.id>`. |

---

## Architecture

Follows the project's MVT rules: business logic in the model layer, thin views,
presentation in templates, routes only in `urls.py`.

### 1. Data model — one new field on `Room`

In [`rooms/models.py`](../../../rooms/models.py), add to `Room`:

```python
is_featured = models.BooleanField(
    default=False,
    db_index=True,
    help_text="Show this room in the Featured Stays carousel on the home page.",
)
```

- One migration (`rooms/migrations/`).
- No change to `Property`. Card rating comes from `room.property.rating` (already exists).

### 2. Selection logic — model manager (single source of truth)

Add a `RoomQuerySet` / manager method `featured_for_home(min_count=3)` on `Room` so the
rule is unit-testable and lives outside the view.

**Base pool:** rooms that are
- `is_active=True`
- `operational_status="available"`
- have **at least one** `RoomImage` (imageless rooms excluded so cards never break)

**Ordering key (used for both featured and fallback):**
`(-property.rating [nulls last], -created_at)`. Rooms with no `property` sort last and
render with city only + default rating.

**Algorithm:**
1. `featured = base.filter(is_featured=True)` ordered by the key.
2. If `featured.count() >= min_count` → return **all** featured (desktop shows all;
   mobile JS caps the visible set).
3. Else → append highest-rated **non-featured** rooms from the base pool until the list
   reaches `min_count` (3). Return that list.

**Performance:** `select_related('property')` + `prefetch_related('images')` so card
rendering does not trigger N+1 queries (~2 queries total).

**Returns:** a `list[Room]` (not a lazy queryset, since featured + fallback are
concatenated).

### 3. Home page wiring — `core/views.py`

In `home_page`, delete the hardcoded `featured = [...]` block and replace with:

```python
from rooms.models import Room
featured_rooms = Room.objects.featured_for_home()
```

Pass `featured_rooms` to the template context (replacing `featured`). View stays thin —
all logic is in the manager.

### 4. Template + mobile "View more" — `templates/pages/index.html`

The Featured Stays card loop iterates **real `Room` objects** instead of dicts:

| Card slot (old dict key) | New source |
|--------------------------|------------|
| `c.images` | `room.images.all` (RoomImage Meta already orders primary-first) |
| `c.name` | `room.name` |
| `c.area_short` (tag) | `room.city` |
| `c.area` | `room.property.address` (fallback to `room.property.name`) |
| `c.rating` (tag) | `room.property.rating` |
| card click / "Book now" | `{% url 'rooms:room-detail-page' %}?id={{ room.id }}` |

Guard against a null `room.property` in the template (show city-only, default rating).

**Mobile "View more":**
- Desktop (`tt-grid-3`) renders every featured room; the grid wraps to additional rows.
- Cards beyond the 3rd get a class (e.g. `tt-featured-extra`).
- A CSS media query hides `.tt-featured-extra` on mobile and reveals a "View more stays"
  button (button itself hidden on desktop).
- A few lines of JS toggle the hidden cards' visibility on tap. No new dependencies.

### 5. Admin star toggle — both panels

Both panels already have a room-action view that handles `action` POSTs (e.g.
`toggle_active`) and returns `JsonResponse`:
- Employee Admin: `room_edit` in [`employeeadmin/views.py`](../../../employeeadmin/views.py)
- Super Admin: `room_update` in [`superadmin/views.py`](../../../superadmin/views.py) (line ~452)

Add a parallel `toggle_featured` branch to **each**:

```python
elif action == 'toggle_featured':
    room.is_featured = not room.is_featured
    room.save(update_fields=['is_featured'])
    return JsonResponse({
        'message': f'Room {"featured" if room.is_featured else "unfeatured"}.',
        'is_featured': room.is_featured,
    })
```

- **Employee scoping is preserved automatically:** the employee `room_edit` already
  resolves the room through the assigned-properties scope (`_assigned_rooms` /
  `get_object_or_404`), so an employee cannot feature a room outside their properties.
- **UI:** add a ★ star button to each room row in both `rooms.html` templates
  (`templates/employeeadmin/rooms.html`, `templates/superadmin/rooms.html`). Gold/filled
  when featured, outline when not. Calls the existing `roomAction()` JS helper and
  updates the button state from the JSON response — mirroring the existing
  Activate/Deactivate button.

### 6. Routes

No new routes. `toggle_featured` reuses the existing `room_edit` endpoint in each panel.
Card links reuse `rooms:room-detail-page`.

---

## Testing

**Manager logic** (`rooms/tests.py`):
- No featured rooms → returns 3 highest-rated active rooms.
- 1–2 featured → returns those featured + fallback fill up to 3.
- ≥3 featured → returns all featured (count > 3 supported).
- Starred-but-imageless room → excluded.
- Inactive / non-`available` rooms → excluded.
- Ordering → higher `property.rating` appears first.

**Admin toggle** (`employeeadmin/tests.py`, `superadmin/tests.py`):
- `toggle_featured` flips `is_featured` and returns the new state.
- Employee admin blocked (404/forbidden) when targeting a room outside assigned
  properties.

---

## Rollout

1. Add field + migration.
2. Add manager method + tests (TDD).
3. Wire home view + template + mobile toggle.
4. Add admin star buttons + `toggle_featured` in both panels + tests.
5. Manual check: star/unstar a room, reload home, confirm card appears and deep-links.

No data backfill needed — `is_featured` defaults to `False`, and the fallback guarantees
the carousel is never empty on day one.
