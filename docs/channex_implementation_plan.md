# Channex PMS Certification — Implementation Plan

> Branch: `bugfixes/render-deploy`  
> All HTML gap analysis findings verified against actual code.

---

## What the certification actually checks

Channex does a **live screenshare** where they watch you make a change in your admin UI and verify the correct API call fires automatically. No Postman, no test scripts — real admin UI → real Channex call.

Three outbound endpoints + one inbound flow:

| Direction | Endpoint | Purpose |
|-----------|----------|---------|
| Outbound | `POST /availability` | Room count per date |
| Outbound | `POST /rates` | Price per night per rate plan |
| Outbound | `POST /restrictions` | min_stay, stop_sell, CTA, CTD |
| Inbound | Webhook → `GET /booking_revisions/:id` → `POST /booking_acknowledge` | Receive bookings |

---

## Phase 0 — External setup (no code, do this first)

These block everything else. Must be done before any coding.

**0.1 — Channex staging account**
- Create account at channex.io (staging/sandbox)
- Create a test property with:
  - Room Type: **Twin Room** (occupancy 2)
  - Room Type: **Double Room** (occupancy 2)
  - Rate Plan per room: **Best Available Rate** 
  - Rate Plan per room: **Bed & Breakfast** (optional, ask client if needed)
- Record all UUIDs: property_id, room_type_id (×2), rate_plan_id (×2+)

**0.2 — Confirm from Channex docs**
- Exact payload shape for `/availability`, `/rates`, `/restrictions`
- Webhook authentication scheme (the current HMAC code is assumed, not confirmed)
- Exact webhook event names
- Rate limit numbers (the cert says "20 ARI/min" — verify)
- Staging base URL

**0.3 — Client decisions needed**
- D1: Which restrictions to support? (min_stay is safest minimum; stop_sell recommended)
- D2: One rate plan or two (BAR + B&B)?  
- D3: Which TTR room types map to Twin/Double for the test property?
- D4: Do `cleaning`/`maintenance`/`out_of_order` rooms count as unavailable for Channex?

---

## Phase 1 — Foundation (no existing code works without this)

### Step 1.1 — ID mapping model

**New file:** `core/ota/models.py`

```python
# Three mapping tables — all stored, never hardcoded

class ChannexProperty(models.Model):
    property = models.OneToOneField('rooms.Property', on_delete=models.CASCADE)
    channex_property_id = models.UUIDField()
    is_active = models.BooleanField(default=True)

class ChannexRoomType(models.Model):
    # Maps N physical Room rows → 1 Channex room type UUID
    property_mapping = models.ForeignKey(ChannexProperty, on_delete=models.CASCADE)
    room_type = models.CharField(max_length=10)  # "single"/"double"/"deluxe"
    channex_room_type_id = models.UUIDField()

class ChannexRatePlan(models.Model):
    room_type_mapping = models.ForeignKey(ChannexRoomType, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)       # "BAR", "B&B"
    channex_rate_plan_id = models.UUIDField()
    is_default = models.BooleanField(default=False)
```

Add admin registration so UUIDs can be entered via Django admin.  
Run `makemigrations` + `migrate`.

### Step 1.2 — Restriction fields

Add to `RoomRate` model (or new `RoomRestriction` model):

```python
min_stay     = models.PositiveSmallIntegerField(null=True, blank=True)
max_stay     = models.PositiveSmallIntegerField(null=True, blank=True)
stop_sell    = models.BooleanField(default=False)
closed_to_arrival   = models.BooleanField(default=False)
closed_to_departure = models.BooleanField(default=False)
```

Run `makemigrations` + `migrate`.

### Step 1.3 — Fix Channex client (rewrite `core/ota/channex.py`)

Replace the current broken client with:

```python
# Three separate methods, correct endpoints, raises on failure

def push_availability(self, property_uuid, room_type_uuid, date_counts: dict) -> None:
    # date_counts = {"2026-10-01": 3, "2026-10-02": 2, ...}
    # POST /availability  — raises ChannexAPIError on 4xx/5xx
    # Caller (outbox worker) handles retry

def push_rates(self, property_uuid, rate_plan_uuid, date_rates: dict) -> None:
    # date_rates = {"2026-10-01": "100.00", ...}
    # POST /rates

def push_restrictions(self, property_uuid, rate_plan_uuid, date_restrictions: dict) -> None:
    # POST /restrictions

def fetch_booking_revision(self, revision_id: str) -> dict:
    # GET /booking_revisions/{revision_id}

def acknowledge_booking(self, revision_id: str) -> None:
    # POST /booking_acknowledge
```

Key rules:
- **Raise `ChannexAPIError` on any failure** — never return `{"success": False}`
- Classify `429` and `5xx` as retryable vs `4xx` as non-retryable
- Remove mock/dry-run mode; log clearly when API key is missing and raise
- No hardcoded UUIDs; always receive them as arguments

### Step 1.4 — Fix worker setup (deployment)

**`Procfile`** — add worker line:
```
web:    gunicorn hotel_booking.wsgi --log-file -
worker: python manage.py qcluster
```

**`render.yaml`** — add a second service:
```yaml
- type: worker
  name: ttr-v2-worker
  plan: free   # upgrade to paid for production
  runtime: python
  buildCommand: "./build.sh"
  startCommand: "python manage.py qcluster"
  # ... same envVars as web
```

> **Note:** Free tier on Render sleeps after inactivity. For the certification screenshare, run locally + ngrok tunnel, or upgrade to a paid instance.

---

## Phase 2 — Outbound engine

### Step 2.1 — Per-date availability calculator

**New function in `core/ota/channex.py`:**

```python
def compute_per_date_availability(room_type: str, property_id, start: date, end: date) -> dict:
    """
    Returns {date_str: count} for every night from start to end-1.
    Each night is computed independently (a room may be free Mon but booked Tue).
    """
    result = {}
    current = start
    while current < end:
        next_day = current + timedelta(days=1)
        count = ChannexManager.calculate_available_count(room_type, current, next_day, property_id)
        result[current.isoformat()] = count
        current = next_day
    return result
```

### Step 2.2 — ARI Change outbox model

**New model in `core/ota/models.py`:**

```python
class ARIChange(models.Model):
    CHANGE_AVAILABILITY = "availability"
    CHANGE_RATES        = "rates"
    CHANGE_RESTRICTIONS = "restrictions"
    CHANGE_TYPE_CHOICES = [...]

    STATUS_PENDING   = "pending"
    STATUS_SENT      = "sent"
    STATUS_FAILED    = "failed"

    property_mapping = models.ForeignKey(ChannexProperty, on_delete=models.CASCADE)
    change_type      = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES)
    room_type        = models.CharField(max_length=10)  # internal type
    date_from        = models.DateField()
    date_to          = models.DateField()
    status           = models.CharField(max_length=10, default=STATUS_PENDING)
    retry_count      = models.PositiveSmallIntegerField(default=0)
    next_retry_at    = models.DateTimeField(default=timezone.now)
    created_at       = models.DateTimeField(auto_now_add=True)
    error_detail     = models.TextField(blank=True, default="")
```

### Step 2.3 — Outbox worker task

**New task in `core/ota/tasks.py`:**

```python
def process_ari_outbox():
    """
    Runs every minute via django-q schedule.
    Coalesces pending ARIChange rows → batches by property+type → fires ≤20 calls/min.
    Retries with exponential backoff on ChannexAPIError (retryable).
    """
    # 1. Fetch pending rows where next_retry_at <= now, ordered by created_at
    # 2. Group by (property, change_type, room_type) — coalesce date ranges
    # 3. Resolve Channex UUIDs via mapping models
    # 4. Call push_availability / push_rates / push_restrictions
    # 5. On success: mark sent
    # 6. On 429/5xx: increment retry_count, set next_retry_at with backoff (30s, 60s, 120s...)
    # 7. On 4xx non-retryable: mark failed, log error
    # Respect 20 calls/min limit — stop after 18 calls, remainder picked up next minute
```

Register in `rooms/apps.py` (or new `core/apps.py`):
```python
Schedule.objects.update_or_create(
    func="core.ota.tasks.process_ari_outbox",
    defaults={"schedule_type": Schedule.MINUTES, "minutes": 1, "repeats": -1}
)
```

### Step 2.4 — Central `record_ari_change()` helper

**New function in `core/ota/tasks.py`:**

```python
def record_ari_change(room_type: str, property_id, date_from: date, date_to: date,
                      change_types=("availability",)):
    """
    Single entry point called from all change paths.
    Creates ARIChange rows; the outbox worker picks them up.
    Does nothing if no ChannexProperty mapping exists for this property.
    """
    mapping = ChannexProperty.objects.filter(property_id=property_id, is_active=True).first()
    if not mapping:
        return
    for ct in change_types:
        ARIChange.objects.create(
            property_mapping=mapping,
            change_type=ct,
            room_type=room_type,
            date_from=date_from,
            date_to=date_to,
        )
```

---

## Phase 3 — Wire change hooks (every path that edits ARI)

Call `record_ari_change(...)` after every save. No exceptions.

### 3.1 — Booking events (already partial, fix gaps)

| File | Event | Fix needed |
|------|-------|-----------|
| `rooms/services.py:141` | Walk-in booking | Change `async_task(sync_ota...)` → `record_ari_change(...)` |
| `payments/services.py:102` | Online booking confirmed | Same |
| `core/ota/processor.py:210,290,323` | Inbound OTA booking | Same + pass `property_id` (currently missing) |
| `rooms/tasks.py:release_expired_holds` | Hold expires | After `.update()`, loop and call `record_ari_change` for each expired booking's room/dates |

### 3.2 — Admin price edits

| File | Line(s) | What to add after save |
|------|---------|------------------------|
| `superadmin/views.py` | ~607–614 (price_per_night edit) | `record_ari_change(room.room_type, room.property_id, today, today+365, ("rates",))` |
| `superadmin/views.py` | ~930–949 (room create) | Same |
| `employeeadmin/views.py` | ~346–349 (price_per_night edit) | Same |
| `employeeadmin/views.py` | ~314–339 (room create) | Same |

### 3.3 — RoomRate create/delete

| File | Line(s) | What to add |
|------|---------|------------|
| `employeeadmin/views.py:275` | `RoomRate.objects.create(...)` | `record_ari_change(room.room_type, room.property_id, start, end, ("rates",))` |
| `employeeadmin/views.py` | RoomRate delete | Same |

### 3.4 — OTABlock create/delete

| File | Line(s) | What to add |
|------|---------|------------|
| `employeeadmin/views.py:238` | `OTABlock.objects.create(...)` | `record_ari_change(room.room_type, room.property_id, start, end, ("availability",))` |
| `employeeadmin/views.py:245` | OTABlock delete | Same |

### 3.5 — Room operational_status changes

| File | Line(s) | What to add |
|------|---------|------------|
| `superadmin/views.py:587` | status save | `record_ari_change(room.room_type, room.property_id, today, today+365, ("availability",))` |
| `employeeadmin/views.py:194,367` | status save | Same |

### 3.6 — Restriction changes (after Step 1.2)

Any view that saves restriction fields → `record_ari_change(..., ("restrictions",))`

### 3.7 — Django admin `list_editable` override

In `rooms/admin.py`, override `save_model` for `RoomAdmin`:
```python
def save_model(self, request, obj, form, change):
    super().save_model(request, obj, form, change)
    if "price_per_night" in form.changed_data:
        record_ari_change(obj.room_type, obj.property_id, today, today+365, ("rates",))
    if "operational_status" in form.changed_data:
        record_ari_change(obj.room_type, obj.property_id, today, today+365, ("availability",))
```

---

## Phase 4 — Full sync

### Step 4.1 — Full sync function

**New function `core/ota/tasks.py`:**

```python
def full_sync_property(property_id):
    """
    Pushes 500 days of availability + rates + restrictions.
    Two API calls maximum (one per endpoint type, batched).
    Should be called manually from admin OR on nightly schedule (≤1/24h).
    """
    start = date.today()
    end = start + timedelta(days=500)
    # Build per-date availability dict for all room types
    # Build per-date rates dict for all rate plans
    # Build per-date restrictions dict
    # Call push_availability, push_rates, push_restrictions
```

Add a management command or superadmin UI button to trigger this.

Register nightly schedule in `rooms/apps.py`:
```python
Schedule.objects.update_or_create(
    func="core.ota.tasks.full_sync_property",
    defaults={"schedule_type": Schedule.DAILY, "repeats": -1}
)
```

---

## Phase 5 — Inbound booking flow (rebuild)

### Step 5.1 — Fix webhook view (`core/ota/views.py`)

Current: treats webhook body as the booking data.  
Fix: treat webhook as a **notification only** — extract the revision ID, enqueue a fetch task.

```python
def post(self, request, *args, **kwargs):
    # 1. Verify signature (confirm scheme against Channex docs first)
    # 2. Parse body — extract revision_id only
    # 3. Enqueue: async_task("core.ota.tasks.process_booking_revision", revision_id)
    # 4. Return 200 immediately
```

### Step 5.2 — Rebuild processor (`core/ota/processor.py`)

```python
def process_booking_revision(revision_id: str):
    """
    1. GET /booking_revisions/{revision_id}   — fetch actual booking data
    2. Parse action: created / modified / cancelled
    3. Apply to local Booking model (existing logic, mostly reusable)
    4. POST /booking_acknowledge with revision_id   ← THIS IS MISSING TODAY
    5. record_ari_change for affected dates
    """
```

### Step 5.3 — Fix idempotency key

Current bug: idempotency key uses `payload["id"]` which is the **booking id**, so created/modified/cancelled for the same booking all share the same key — only the first is processed.

Fix: key must be `revision_id` (unique per event), not `booking_id`.

### Step 5.4 — Feed poll backup

Add a scheduled task (every 15 min) that polls `/booking_revisions` for unacknowledged revisions — safety net in case the webhook misses.

```python
# In rooms/apps.py
Schedule.objects.update_or_create(
    func="core.ota.tasks.poll_booking_revisions_feed",
    defaults={"schedule_type": Schedule.MINUTES, "minutes": 15, "repeats": -1}
)
```

---

## Phase 6 — Test + certify

### Step 6.1 — Seed staging data
- Enter Channex staging UUIDs into the mapping models via Django admin
- Create varied room rates (not all the same price) across 500 days

### Step 6.2 — Run tests 1–10 from admin UI
- Test 1: Trigger full sync from admin → check Channex dashboard for 500 days of data
- Test 2: Change one price in admin → verify 1 Channex call fires
- Test 3–4: Change multiple dates → verify batched into 1 call
- Test 5–7: Change restrictions → verify `/restrictions` call
- Test 8: Set a 6-month `RoomRate` → verify 1 call
- Test 9–10: Create/cancel a booking → verify per-date availability push

### Step 6.3 — Test 11 (inbound booking)
- Use Channex's test Booking.com account to send a test reservation
- Verify: webhook fires → revision fetch → booking saved → acknowledged
- Screenshot the booking in the admin and the acknowledgement in logs

### Step 6.4 — Submit form
- Submit task IDs + screenshots to `https://forms.gle/xA8F3eSYBPBd8apYA`
- Answer Test 14 extra notes (min-stay type, PCI — Razorpay handles cards, no card data stored)

---

## Summary of files to change

| File | Type of change |
|------|---------------|
| `core/ota/models.py` | **New** — mapping models + ARIChange outbox |
| `core/ota/channex.py` | **Rewrite** — correct endpoints, raise on failure, no mock |
| `core/ota/tasks.py` | **New** — outbox worker, full sync, feed poll, record_ari_change |
| `core/ota/processor.py` | **Rewrite** — revision fetch + acknowledge, fix idempotency |
| `core/ota/views.py` | **Rewrite** — webhook as notification only |
| `rooms/models.py` | **Add** restriction fields to RoomRate |
| `rooms/tasks.py` | **Fix** — release_expired_holds must call record_ari_change |
| `rooms/services.py` | **Fix** — swap async_task(sync_ota) → record_ari_change |
| `rooms/apps.py` | **Add** new scheduled jobs |
| `payments/services.py` | **Fix** — swap async_task(sync_ota) → record_ari_change |
| `superadmin/views.py` | **Add** record_ari_change after every price/status save |
| `employeeadmin/views.py` | **Add** record_ari_change after every price/status/rate/block save |
| `rooms/admin.py` | **Add** save_model overrides |
| `Procfile` | **Add** worker line |
| `render.yaml` | **Add** worker service |
| `.env.example` | **Add** CHANNEX_API_KEY, CHANNEX_WEBHOOK_SECRET |

---

## Order of execution

```
Phase 0 (external)  →  Phase 1 (foundation: models + client + worker setup)
                     →  Phase 2 (outbound engine: per-date calc + outbox)
                     →  Phase 3 (change hooks: all admin paths)
                     →  Phase 4 (full sync)
                     →  Phase 5 (inbound rebuild)
                     →  Phase 6 (test + certify)
```

Phases 1–4 can be done before Channex staging account is ready except for the UUID values.  
Phase 0 must be resolved before any end-to-end testing.
