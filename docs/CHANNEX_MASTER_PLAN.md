# Channex PMS Certification — Master Development Plan

> **Repo:** TTR-V2 · **Branch base:** `bugfixes/render-deploy`
> **Goal:** Pass Channex PMS certification (13 tests + live screenshare).
> **This document is the single source of truth for the whole team.** Do not start coding until you have read §0–§4.
> **Status of analysis:** Every claim below was verified against the actual code (file + line). Nothing here is assumed.

---

## Status legend

| Symbol | Meaning |
|--------|---------|
| ✅ Done | Works and is correct |
| 🟡 Partial | Exists but incomplete |
| ⚠️ Wrong | Exists but built incorrectly / on wrong assumptions |
| ❌ Missing | Does not exist |

---

## §0 — TL;DR for the team

The Channex integration in this repo is a **skeleton built on unverified assumptions**. The folder structure (`core/ota/`) and the abstract interface (`core/ota/base.py`) are a reasonable start, but:

- **Outbound sync** sends to a wrong/invented endpoint, wrong granularity, wrong IDs → ⚠️
- **Change detection** only fires on bookings; admin price/rate/block edits fire nothing → ❌
- **No outbox, no batching, no retry, no rate limiting** → ❌
- **No ID mapping** (sends `"single"` where Channex needs a UUID) → ❌
- **Inbound bookings** never fetch revisions and never acknowledge → ⚠️
- **The background worker is never started in production** → ❌ (this alone means nothing runs today)

We are rebuilding the integration properly, in **6 parallel workstreams**. This document defines the **contracts** (§3) so you can work independently, the **workstream ownership** (§4), and the **migration strategy** (§2) so we don't collide.

---

## §1 — Current state audit (what exists, what's wrong)

### 1.1 — Verified findings

| # | Area | File · Line | State | Problem |
|---|------|-------------|-------|---------|
| F1 | Worker in production | [`Procfile`](Procfile), [`render.yaml`](render.yaml) | ❌ | Only a `web` process. No `qcluster`. Every `async_task` is queued but **never consumed**. |
| F2 | Error handling | [`core/ota/channex.py:100`](core/ota/channex.py#L100), [`:140`](core/ota/channex.py#L140) | ⚠️ | Catches errors, returns `{"success": False}`. Never raises. |
| F3 | Task retry | [`rooms/tasks.py:105`](rooms/tasks.py#L105) | ⚠️ | Returns `res.get("success", False)`. django-q sees a return value → marks task **successful** → never retries. 429/5xx lost silently. |
| F4 | Mock mode | [`core/ota/channex.py:75`](core/ota/channex.py#L75), [`:115`](core/ota/channex.py#L115) | ⚠️ | Empty API key → returns fake success. Misconfigured prod looks healthy. |
| F5 | ID mapping | entire repo | ❌ | No mapping model. Payload sends `room_type_id = "single"` ([`channex.py:85`](core/ota/channex.py#L85)). Channex needs UUIDs. |
| F6 | Endpoint | [`core/ota/channex.py:81`](core/ota/channex.py#L81), [`:121`](core/ota/channex.py#L121) | ⚠️ | POSTs to `/ari`. Real endpoints are `/availability`, `/rates`, `/restrictions`. |
| F7 | Availability granularity | [`core/ota/channex.py:151`](core/ota/channex.py#L151) | ⚠️ | One count for the whole date range. Channex needs **per-date** counts. |
| F8 | Currency | [`core/ota/channex.py:128`](core/ota/channex.py#L128) | ⚠️ | INR string, no currency handling. Test property is USD. |
| F9 | Restriction model | [`rooms/models.py`](rooms/models.py) | ❌ | No `min_stay`, `max_stay`, `stop_sell`, `CTA`, `CTD` fields anywhere. |
| F10 | Change detection | [`superadmin/views.py`](superadmin/views.py), [`employeeadmin/views.py`](employeeadmin/views.py), [`rooms/admin.py`](rooms/admin.py) | ❌ | **No admin path calls the channel manager.** Confirmed by grep. |
| F11 | Outbox / batching | entire repo | ❌ | One `async_task` per event. No coalescing, no rate limiter. |
| F12 | Inbound revisions | [`core/ota/processor.py:111`](core/ota/processor.py#L111) | ⚠️ | Parses booking from webhook body. Never fetches `/booking_revisions/:id`. |
| F13 | Booking acknowledge | [`core/ota/views.py:56`](core/ota/views.py#L56) | ❌ | The `"acknowledged"` string is the HTTP response, **not** the Channex `POST /booking_acknowledge` call. |
| F14 | Webhook signature | [`core/ota/channex.py:40`](core/ota/channex.py#L40), [`views.py:26`](core/ota/views.py#L26) | ⚠️ | HMAC-SHA256 `X-Channex-Signature` scheme is **assumed, not confirmed** against docs. |
| F15 | Full sync | entire repo | ❌ | No 500-day full-sync function. |
| F16 | Scheduled jobs | [`rooms/apps.py:13`](rooms/apps.py#L13) | 🟡 | Only holds/complete/loyalty schedules. No full-sync, no feed-poll. |
| F17 | `.env.example` | [`.env.example`](.env.example) | ❌ | No `CHANNEX_*` variables documented (settings default them to `""`). |

### 1.2 — Extra bugs found (beyond the original gap analysis)

| # | Bug | File · Line | Impact |
|---|-----|-------------|--------|
| B1 | **Idempotency key drops modifications** | [`core/ota/views.py:45`](core/ota/views.py#L45) | Key falls back to `payload["id"]` (the booking id). A create then a modify for the same booking share the key → modify is rejected as a duplicate and **never processed**. |
| B2 | **Cross-property inventory contamination** | [`core/ota/processor.py:210`](core/ota/processor.py#L210), [`:290`](core/ota/processor.py#L290), [`:323`](core/ota/processor.py#L323) | Inbound OTA sync calls `_enqueue_inventory_sync(room.room_type, …)` **without `property_id`** → availability is computed across ALL properties for that type. (Walk-in/payment paths correctly pass it.) |
| B3 | **Expired holds free inventory silently** | [`rooms/tasks.py:16`](rooms/tasks.py#L16) | Bulk `.update(status="expired")` frees rooms but pushes nothing to Channex. This is the most frequent inventory change in the system (every abandoned checkout). |
| B4 | **Modify-on-miss re-creates** | [`core/ota/processor.py:228`](core/ota/processor.py#L228) | `_handle_booking_modified` calls `_handle_booking_created` when booking not found — fragile combined with B1. |

### 1.3 — What is actually ✅ and can be reused

- The abstract `ChannelManager` interface pattern ([`core/ota/base.py`](core/ota/base.py)) — good design, keep it.
- `ProcessedWebhookEvent` idempotency table exists in `payments.models` — reuse it (fix the key, B1).
- The booking model has `ota_reservation_id`, source choices for OTA channels, and OTA source resolution — reusable.
- django-q2 is installed and schedules are registered in `rooms/apps.py` — the mechanism works; we just add jobs.
- The overlap/availability query logic in `calculate_available_count` is correct **per-night** — we wrap it, not replace it.

---

## §2 — Migration coordination strategy (READ THIS — #1 collision risk)

Concurrent Django development breaks most often on **migration conflicts**. Rules:

1. **All model changes are owned by Workstream A only.** Nobody else edits `models.py` in any app.
2. WS-A lands **one migration batch** covering *all* new models and fields (§4 WS-A) on **day 1**, merged to the integration branch **before** other workstreams branch off.
3. After that batch is merged, no further model changes are allowed without posting in the team channel and coordinating a migration slot.
4. If you think you need a new field mid-stream, **do not run `makemigrations`**. Post in the channel; WS-A owner adds it and bumps the migration.
5. Never commit a merge that contains two leaf migrations in the same app. If `makemigrations --merge` is ever needed, WS-A owner runs it.

**Integration branch:** `feature/channex-cert` (branched from `bugfixes/render-deploy`). All workstreams branch from it and PR back into it. `main` is untouched until certification passes.

---

## §3 — Integration contracts (the seams — agree these on day 1)

These are the interfaces that let workstreams build **independently**. They are frozen after day 1. If a signature must change, it goes through the team channel.

### 3.1 — The outbound entry point (used by ALL change hooks)

```python
# core/ota/dispatch.py  — owned by WS-C, STUBBED on day 1 so WS-D can build against it

def record_ari_change(
    room_type: str,             # internal type: "single" | "double" | "deluxe"
    property_id,                # rooms.Property PK (UUID)
    date_from: date,
    date_to: date,              # exclusive end
    change_types=("availability",),   # subset of {"availability","rates","restrictions"}
) -> None:
    """
    Single entry point for every code path that mutates ARI data.
    Creates ARIChange outbox rows. No-ops if the property has no Channex mapping.
    NEVER call the Channex API directly from a view or service — always go through here.
    """
```

> **Day-1 action:** WS-C commits this as a no-op stub (just `pass` + a log line). WS-D immediately builds all hooks against it. When WS-C finishes the real body, hooks light up automatically. No rework.

### 3.2 — The Channex client (used by outbox worker + inbound)

```python
# core/ota/channex.py  — owned by WS-B

class ChannexAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.retryable = status_code == 429 or 500 <= status_code < 600

class ChannexManager(ChannelManager):
    def push_availability(self, property_uuid: str, room_type_uuid: str,
                          date_counts: dict[str, int]) -> str: ...   # returns Channex task id
    def push_rates(self, property_uuid: str, rate_plan_uuid: str,
                   date_rates: dict[str, str]) -> str: ...
    def push_restrictions(self, property_uuid: str, rate_plan_uuid: str,
                          date_restrictions: dict[str, dict]) -> str: ...
    def fetch_booking_revision(self, revision_id: str) -> dict: ...
    def acknowledge_booking(self, revision_id: str) -> None: ...
    # Every method RAISES ChannexAPIError on failure. Never returns {"success": False}.
```

> **Day-1 action:** WS-B commits these signatures raising `NotImplementedError`. WS-C (outbox) and WS-E (inbound) build against the signatures.

### 3.3 — The mapping resolver (used by client callers)

```python
# core/ota/mapping.py  — owned by WS-A

def resolve_property(property_id) -> str | None: ...          # → Channex property UUID
def resolve_room_type(property_id, room_type) -> str | None:  # → Channex room_type UUID
def resolve_rate_plans(property_id, room_type) -> list[RatePlanMap]: ...
```

### 3.4 — Frozen data-flow (everyone follows this shape)

```
ADMIN EDIT / BOOKING EVENT
        │
        ▼
record_ari_change()        ← §3.1  (the ONLY way to trigger outbound)
        │  writes rows
        ▼
   ARIChange (outbox table)
        │  every 1 min
        ▼
process_ari_outbox()       ← coalesce + batch + rate-limit (≤20/min)
        │  resolves UUIDs via §3.3
        ▼
ChannexManager.push_*()    ← §3.2  (raises on failure → worker retries w/ backoff)
        │
        ▼
     Channex API


CHANNEX WEBHOOK  →  view extracts revision_id  →  async task:
        fetch_booking_revision()  →  save Booking  →  acknowledge_booking()  →  record_ari_change()
```

---

## §4 — Workstreams (ownership, dependencies, tasks)

Six workstreams. **Day-1 sequencing:** WS-A merges models, WS-B + WS-C merge stubs (§3). Then A–F run in parallel.

```
Dependency graph:
  WS-A (models/mapping) ──┬──▶ WS-C (outbox engine) ──▶ WS-D (change hooks)
                          ├──▶ WS-E (inbound flow)
  WS-B (client) ──────────┘
  WS-F (infra/deploy) ── independent, anytime
```

---

### WS-A — Foundation: models, migrations, mapping · Owner: ____

**Blocks:** everyone. Land first.

**Files:**
- **New** `core/ota/models.py`
- **New** `core/ota/mapping.py` (§3.3 resolver)
- **Edit** `rooms/models.py` — add restriction fields (the ONLY model edit outside `core/ota`)
- **New/Edit** `core/ota/admin.py` — register mapping models
- **New** `core/apps.py` or reuse `core/` app config for migrations

**Tasks:**
1. `ChannexProperty` (property OneToOne → channex_property_id UUID, is_active).
2. `ChannexRoomType` (FK ChannexProperty, room_type str, channex_room_type_id UUID).
3. `ChannexRatePlan` (FK ChannexRoomType, name, channex_rate_plan_id UUID, is_default, base_price).
4. `ARIChange` outbox model — fields: property_mapping FK, change_type, room_type, date_from, date_to, status (pending/sent/failed), retry_count, next_retry_at, error_detail, created_at. Index on `(status, next_retry_at)`.
5. Add restriction fields to `RoomRate` (or a new `RoomRestriction` model — **team decision D1**): `min_stay`, `max_stay`, `stop_sell`, `closed_to_arrival`, `closed_to_departure`.
6. Implement `mapping.py` resolvers (§3.3).
7. Register all mapping models in Django admin so UUIDs are entered by hand.
8. **Run `makemigrations` once, commit the migration, merge first.**

**Definition of done:** migrations apply cleanly on a fresh DB; mapping resolvers return correct UUIDs given seeded data; admin screens editable.

---

### WS-B — Channex client rewrite · Owner: ____

**Depends on:** §3.2 contract + Channex API docs (§0.2 external).

**Files:** **Rewrite** `core/ota/channex.py`

**Tasks:**
1. Implement the 5 methods in §3.2 against real endpoints (`/availability`, `/rates`, `/restrictions`, `/booking_revisions/:id`, `/booking_acknowledge`).
2. `ChannexAPIError` with `.retryable` (429 + 5xx).
3. **Remove mock/dry-run mode.** If API key missing: log error + raise (do not fake success). Fixes F4.
4. Confirm and implement the real webhook signature scheme (F14) — verify against docs before coding.
5. Handle currency correctly (F8) — send the property's configured currency.
6. Unit tests mocking `requests` for each method (success + 429 + 5xx + 4xx).

**Definition of done:** each method hits the correct URL with correct payload shape; raises `ChannexAPIError` with correct `.retryable`; tests green.

---

### WS-C — Outbound engine: per-date calc + outbox worker · Owner: ____

**Depends on:** WS-A models, WS-B client (can use stub until B lands).

**Files:**
- **New** `core/ota/dispatch.py` (§3.1 — commit stub day 1)
- **New** `core/ota/tasks.py`
- **New** `core/ota/availability.py` (per-date calc)
- **Edit** `rooms/apps.py` (register the outbox schedule)

**Tasks:**
1. **Day 1:** commit `record_ari_change()` stub (§3.1) so WS-D unblocks.
2. `compute_per_date_availability(room_type, property_id, start, end) -> dict[str,int]` — wraps the existing per-night `calculate_available_count` (reuse [`channex.py:151`](core/ota/channex.py#L151) logic, fixes F7). Respect **team decision D4** (do cleaning/maintenance rooms count?).
3. Rate/restriction per-date builders.
4. Real `record_ari_change()` body — write `ARIChange` rows; no-op if no mapping.
5. `process_ari_outbox()` scheduled task (every 1 min):
   - fetch pending rows where `next_retry_at <= now`
   - coalesce by `(property, change_type, room_type)`, merge date ranges
   - resolve UUIDs via §3.3
   - call `push_*`; on success mark `sent`; on `ChannexAPIError.retryable` → backoff (30s→60s→120s…, cap retries); on non-retryable → `failed`
   - **stop after 18 calls/min** to respect the 20/min limit (fixes F11)
6. Register schedule in `rooms/apps.py` (Schedule.MINUTES, 1).

**Definition of done:** editing seeded data creates outbox rows; worker coalesces N edits into 1 call; forced 429 triggers backoff not data loss; ≤20 calls/min enforced.

---

### WS-D — Change hooks: wire every ARI-mutating path · Owner: ____

**Depends on:** only the §3.1 stub (fully parallel from day 1).

**Rule:** after every save that changes availability/rates/restrictions, call `record_ari_change(...)`. Never call the Channex API directly.

**Files & exact locations:**

| Path | File · Line | change_types |
|------|-------------|--------------|
| Walk-in booking | [`rooms/services.py:141`](rooms/services.py#L141) | replace `async_task(sync_ota…)` → `record_ari_change(..., ("availability",))` |
| Online booking confirmed | [`payments/services.py:102`](payments/services.py#L102) | same |
| Inbound OTA booking (×3) | [`core/ota/processor.py:210`](core/ota/processor.py#L210), [`:290`](core/ota/processor.py#L290), [`:323`](core/ota/processor.py#L323) | same **+ pass property_id** (fixes B2) |
| Expired holds | [`rooms/tasks.py:16`](rooms/tasks.py#L16) | after `.update()`, iterate expired rooms → `record_ari_change(..., ("availability",))` (fixes B3) |
| Super price edit | [`superadmin/views.py:607`](superadmin/views.py#L607), [`:614`](superadmin/views.py#L614) | `("rates",)` |
| Super room create | [`superadmin/views.py:930`](superadmin/views.py#L930) | `("availability","rates")` |
| Super room status | [`superadmin/views.py:587`](superadmin/views.py#L587) | `("availability",)` |
| Emp price edit | [`employeeadmin/views.py:346`](employeeadmin/views.py#L346) | `("rates",)` |
| Emp room create | [`employeeadmin/views.py:314`](employeeadmin/views.py#L314) | `("availability","rates")` |
| Emp room status | [`employeeadmin/views.py:194`](employeeadmin/views.py#L194), [`:367`](employeeadmin/views.py#L367) | `("availability",)` |
| Emp RoomRate create | [`employeeadmin/views.py:275`](employeeadmin/views.py#L275) | `("rates",)` |
| Emp OTABlock create | [`employeeadmin/views.py:238`](employeeadmin/views.py#L238) | `("availability",)` |
| Emp OTABlock delete | [`employeeadmin/views.py:245`](employeeadmin/views.py#L245) | `("availability",)` |
| Restriction edits | wherever WS-A's restriction fields are saved | `("restrictions",)` |
| Django admin inline edit | [`rooms/admin.py:61`](rooms/admin.py#L61) | override `save_model`: on `price_per_night` change → `("rates",)`; on `operational_status` change → `("availability",)` |

**Definition of done:** every listed path creates an outbox row on save (verify with the WS-C stub logging, then the real worker). Fixes F10.

---

### WS-E — Inbound booking flow rebuild · Owner: ____

**Depends on:** WS-B client, WS-A mapping.

**Files:** **Rewrite** `core/ota/views.py`, **Rewrite** `core/ota/processor.py`

**Tasks:**
1. Webhook view = **notification only**: verify signature, extract `revision_id`, enqueue `async_task("core.ota.processor.process_booking_revision", revision_id)`, return 200. (Fixes F12 shape.)
2. **Fix idempotency key (B1):** key on `revision_id`, not booking id. Reuse `ProcessedWebhookEvent`.
3. `process_booking_revision(revision_id)`:
   - `fetch_booking_revision()` (F12)
   - parse action created/modified/cancelled (reuse existing save logic in processor — it's mostly fine)
   - save Booking
   - **`acknowledge_booking(revision_id)`** (fixes F13)
   - `record_ari_change(...)` for affected dates (with property_id)
4. Feed-poll backup task `poll_booking_revisions_feed()` every 15 min for unacknowledged revisions (fixes F16 inbound half). Register in `rooms/apps.py`.

**Definition of done:** a test reservation flows webhook → fetch → save → acknowledge; duplicate webhook is idempotent; a modify after a create is processed (B1 gone).

---

### WS-F — Infra / deployment · Owner: ____

**Depends on:** nothing. Do anytime.

**Files:** `Procfile`, `render.yaml`, `.env.example`, `hotel_booking/settings/*`

**Tasks:**
1. `Procfile`: add `worker: python manage.py qcluster` (fixes F1).
2. `render.yaml`: add a `worker` service running `python manage.py qcluster` with the same env vars (fixes F1). Note free tier sleeps — flag paid instance / local tunnel for the screenshare.
3. `.env.example`: add `CHANNEX_API_KEY`, `CHANNEX_API_URL`, `CHANNEX_WEBHOOK_SECRET` (fixes F17).
4. Settings: env-specific staging vs prod Channex URL; ensure `Q_CLUSTER` retry config is sane for the new raising client.
5. Document the local `qcluster` + tunnel setup for certification day.

**Definition of done:** `qcluster` runs alongside web locally and on Render; queued tasks actually execute.

---

## §5 — Full sync (cross-cutting, after WS-C) · Owner: ____

**Files:** `core/ota/tasks.py`, superadmin UI button or management command, `rooms/apps.py`.

**Tasks:**
1. `full_sync_property(property_id)` — 500 days of availability + rates + restrictions, batched (≤2 calls per endpoint type). Fixes F15.
2. Manual trigger (admin button / `manage.py channex_full_sync`).
3. Nightly schedule (Schedule.DAILY, off-peak, ≤1/24h — Test 13). Fixes F16.

---

## §6 — External blockers (must resolve before end-to-end testing) · Owner: ____

Not code. Do in parallel with early coding.

1. Channex **staging** account + test property: Twin Room + Double Room (occupancy 2 each), rate plans BAR ($100) + B&B ($120). Record all UUIDs.
2. Read Channex docs; confirm: exact `/availability` `/rates` `/restrictions` payloads, webhook signature scheme, event names, rate-limit numbers, staging base URL.
3. Seed the mapping models (WS-A) with the recorded UUIDs.

**Team decisions to lock before coding the relevant workstream:**
- **D1** (WS-A): which restrictions to support (min_stay minimum; stop_sell recommended).
- **D2** (WS-A/WS-C): one rate plan per type, or two (BAR + B&B)?
- **D3** (WS-A/§6): which TTR room types map to Twin / Double?
- **D4** (WS-C): do `cleaning`/`maintenance`/`out_of_order` rooms count as unavailable for Channex?
- **D5** (WS-C): source of the type-level price (base `price_per_night` vs a dedicated rate).

---

## §7 — Integration & merge order

1. **WS-A** models + migration → merge to `feature/channex-cert` first.
2. **WS-B** client stub + **WS-C** `record_ari_change` stub → merge (unblocks D & E).
3. WS-B real client, WS-C real engine, WS-D hooks, WS-E inbound, WS-F infra → PR independently into `feature/channex-cert`.
4. §5 full sync after WS-C is merged.
5. Integration test on `feature/channex-cert` (§8) → only then PR to `main`.

**PR rules:** small PRs, one workstream each; no PR may add a migration except WS-A's; every PR green on tests before merge.

---

## §8 — Certification test checklist (map to code)

| Test | How we satisfy it | Owner streams |
|------|-------------------|---------------|
| 1 Full sync | §5 `full_sync_property` | WS-C, §5 |
| 2 Single date/rate | Admin price edit → outbox → 1 `/rates` call | WS-D, WS-C |
| 3 Single date/multi-rate | Outbox coalescing → 1 call | WS-C |
| 4 Multi-date/multi-rate | Coalescing + date ranges | WS-C |
| 5 Min stay | Restriction field → `/restrictions` | WS-A, WS-D, WS-C |
| 6 Stop sell | Restriction field | WS-A, WS-D, WS-C |
| 7 Complex restrictions | CTA/CTD/min/max in 1 call | WS-A, WS-C |
| 8 Half-year | 6-month `RoomRate` → 1 call | WS-D, WS-C |
| 9 Single-date availability | Booking → per-date push | WS-C, WS-D |
| 10 Multi-date availability | per-date push | WS-C |
| 11 Booking + ack | webhook → revision → save → ack | WS-E |
| 12 Rate limits | outbox ≤20/min + backoff | WS-C |
| 13 Delta + nightly full sync | hooks (delta) + §5 nightly | WS-C, §5 |
| 14 Extra notes | Razorpay handles cards; no card data stored | — |

**Live screenshare rehearsal:** change a price and a min-stay in the real admin UI → show the outbox row, the worker firing 1 batched call, the retry on a forced 429, the mapping table (no hardcoded UUIDs), and the webhook→ack sequence.

---

## §9 — Definition of done (whole project)

- [ ] `qcluster` runs in prod; queued tasks execute (F1)
- [ ] All ARI edits flow through `record_ari_change` → outbox → batched Channex call (F10, F11)
- [ ] Client raises on failure; worker retries 429/5xx with backoff (F2, F3)
- [ ] No mock success in prod (F4)
- [ ] Mapping models resolve all UUIDs; no hardcoded IDs (F5)
- [ ] Correct endpoints + per-date granularity + currency (F6, F7, F8)
- [ ] Restriction fields exist and push (F9)
- [ ] Inbound: revision fetch + acknowledge + idempotency fixed (F12, F13, B1)
- [ ] property_id passed on inbound sync (B2); expired holds push (B3)
- [ ] Full sync manual + nightly (F15, F16)
- [ ] `.env.example` documents Channex vars (F17)
- [ ] All 13 tests pass; form submitted with task IDs

---

## §10 — Reference

- Channex cert docs: https://docs.channex.io/api-v.1-documentation/pms-certification-tests
- Submission form: https://forms.gle/xA8F3eSYBPBd8apYA
- Detailed step-level plan: [`docs/channex_implementation_plan.md`](docs/channex_implementation_plan.md)
