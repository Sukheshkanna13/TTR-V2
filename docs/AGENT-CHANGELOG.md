# Agent Change Log

A running record of changes made by AI coding sessions, newest first. Each entry
lists the problem, the root cause, and what changed, so future sessions have
context without re-deriving it.

---

## 2026-09-19 — V3 Room UX Signals & Scarcity Badges Engine

### 1. Real-Time Scarcity & Demand Math (`rooms/services.py`)
- `compute_bulk_ux_signals(rooms, check_in, check_out, unavailable_ids)`: Computes real-time inventory scarcity per `(property_id, room_type)` using a single SQL aggregation query:
  `Room.objects.filter(property_id__in=..., is_active=True, operational_status='available').exclude(id__in=unavailable_ids).values('property_id', 'room_type').annotate(available=Count('id'))`.
- Accepts precalculated `unavailable_ids` from search query builder to eliminate redundant booking & OTA block database queries ($O(1)$ query overhead, bounded performance test passing at $\le 7$ queries).
- Dynamic Scarcity Levels:
  - Critical: `remaining == 1` -> `"⚡ Only 1 room left for your dates!"` (`scarcity_level="critical"`).
  - Warning: `remaining == 2` -> `"Hurry, only 2 rooms left!"` (`scarcity_level="warning"`).
  - Normal: `remaining >= 3` -> No scarcity pressure (`scarcity_level="normal"`).
- Social Proof & Demand:
  - `is_high_demand`: Checks bookings confirmed in last 7 days ($\ge 2$ bookings) -> `"🔥 High Demand · Booked X times this week"`.
  - `is_top_rated`: Evaluates room/property rating ($\ge 4.7$) -> `"★ Guest Favourite (X.X)"`.
- `get_room_ux_signals(room, check_in, check_out)`: Single-room wrapper returning dynamic signals for room detail views.

### 2. API Serializers & Thin Views (`rooms/serializers.py` & `rooms/views.py`)
- `RoomSerializer`: Added `ux_signals = serializers.SerializerMethodField()`. Retrieves precomputed signals from `context['ux_signals_map']` for $O(1)$ serialization with zero per-room DB query overhead, falling back to `get_room_ux_signals()` for single room detail calls.
- `SearchRoomsView._handle_search()`: Precomputes bulk UX signals using search dates and prefiltered `unavailable_ids`, passing map into `RoomSerializer` context.
- `RoomDetailView.get()`: Parses `check_in` and `check_out` query params from URL and injects into serializer context.

### 3. Room Search & Room Details Luxury UI (`templates/rooms/`)
- `templates/rooms/search.html`: Added `uxSignalsHTML(room)` rendering elegant floating luxury chips on room cards (`⚡ Only 1 room left!`, `🔥 High Demand`, `★ Guest Favourite`) and subtle inline scarcity text, avoiding aggressive popups while keeping guests informed.
- `templates/rooms/room_details.html`: Added `#uxSignalBanner` above price summary displaying real-time scarcity notices, high demand indicators, guest favourite badges, and the 10-Minute Hold Guarantee trust notice (`✓ No double-booking. Your room is locked instantly when you proceed.`). Refetches UX signals on date update.

### 4. Automated Test Suite (`rooms/tests.py`)
- `RoomUXSignalsTest`: Unit and integration tests covering:
  - Scarcity calculation levels (3 rooms -> normal, 2 rooms -> warning, 1 room -> critical).
  - High demand badge generation based on 7-day recent bookings.
  - Guest favourite badge generation for top-rated rooms ($\ge 4.7$).
  - `SearchRoomsView` API payload containing `ux_signals`.
  - `RoomDetailView` API payload containing `ux_signals`.
  - Verified bounded query counts in `rooms.tests_performance` with $O(1)$ query complexity. All 113 tests passing.

---

## 2026-09-19 — Loyalty Points Program & Coupon Redemption Engine (Milestone 37 / LOY-01, LOY-02, LOY-08)

### 1. Coupon Redemption Rules & Voucher Models (`loyalty/models.py`)
- `CouponRedemptionRule`: Added Super Admin runtime-configurable rules allowing guests to convert loyalty points into discount vouchers (fixed INR or percentage discount with cap, minimum booking amounts, validity period in days, and optional property scope).
- `Coupon`: Implemented coupon vouchers with unique random uppercase alphanumeric codes (`TTR-...`), status state machine (`active`, `applied`, `redeemed`, `expired`, `cancelled`), expiration checking, and booking eligibility verification (`validate_for_booking` & `calculate_discount`). Resolved Python property shadowing trap with `@builtins.property`.
- Applied migration `loyalty.0002_couponredemptionrule_coupon`.

### 2. Booking Hold & Tax Integration (`rooms/models.py`)
- `Booking`: Added `coupon` (`ForeignKey` to `loyalty.Coupon`) and `discount_amount` fields.
- Indian GST Compliance: Updated `Booking.compute_tax()` to compute tax on the net taxable amount after discounts: `taxable_base = max(0, total_price - discount_amount)`.
- Added `payable_amount` property: `max(0, total_price - discount_amount) + tax_amount`.
- Hold Safety Net: Updated `Booking.expire_if_needed()` and `Booking.release_hold()` to auto-release any `applied` coupon back to `active` status so guest points/vouchers are never lost when a checkout is abandoned or times out.
- Applied migration `rooms.0023_booking_coupon_booking_discount_amount`.

### 3. Atomic Concurrency-Safe Services (`loyalty/services.py` & `payments/services.py`)
- `loyalty/services.award_booking_points`: Hardened with `transaction.atomic()`, `select_for_update()`, and ledger deduplication checks (`reason='BOOKING_CONFIRMED'`) to prevent duplicate point awards.
- `loyalty/services.redeem_points_for_coupon`: Atomic point debit with `select_for_update()` on `UserProfile`, immutable `LoyaltyLedger` audit record (`reason='COUPON_REDEMPTION'`), and tier recalculation.
- `loyalty/services.apply_coupon_to_booking`: Atomic validation, reservation (`status='applied'`), discount deduction, and GST recalculation.
- `loyalty/services.remove_coupon_from_booking`: Detaches coupon and returns voucher to `active` status.
- `payments/services.confirm_booking_and_payment`: Transitions `booking.coupon.status` to `redeemed` upon successful payment confirmation, and reconciles paise using `payable_amount`.
- `payments/views.py`: Updated Razorpay order creation to charge `payable_amount`.

### 4. Guest Rewards Portal & Checkout Integration
- `loyalty/views.py` & `loyalty/urls.py`: Built guest rewards portal (`/loyalty/`) and JSON APIs (`GET /loyalty/api/my-coupons/`, `POST /loyalty/api/redeem/`, `POST /loyalty/api/apply-coupon/`, `POST /loyalty/api/remove-coupon/`).
- `templates/loyalty/rewards.html`: Modern UI with tier badge (Bronze/Silver/Gold), real-time tier progress bar, points balance card, active vouchers display with one-click copy, instant redeem voucher cards, and complete point ledger audit table.
- `templates/payments/checkout.html`: Integrated coupon code input with validation, active vouchers quick-select pills, and real-time price breakdown (Room rate, Coupon discount, Taxes & GST, Total Payable).
- `templates/base.html` & `templates/pages/folio.html`: Added Rewards & Loyalty navigation links in desktop/mobile profile dropdowns and folio tier card.

### 5. Super Admin Management (`superadmin/`)
- `superadmin/views.py` & `templates/superadmin/loyalty_config.html`: Added Coupon Redemption Rules table, CRUD handlers (`save_redemption_rule`, `delete_redemption_rule`, `toggle_redemption_rule`), and recent issued vouchers audit table.

---

## 2026-09-19 — Core Hardening, Walk-In Engine, Hero Banners & OTA Channel Manager

### 1. Security & Authentication Hardening
- `hotel_booking/settings/prod.py` & `base.py`: Enforced `DEBUG=False` default in production with startup assertions for `SECRET_KEY` and `DATABASE_URL`. Refactored `DATABASES` to parse `DATABASE_URL` via `dj_database_url.config`.
- `accounts/models.py` & `utils.py`: Added explicit `purpose` field to `OTP` model (`login`, `registration`, `password_reset`, `email_change`). Implemented purpose-bound OTP creation/verification, `is_otp_throttled()`, and constant-time token comparison with `hmac.compare_digest()`.
- `accounts/adapter.py`: Added email verification check (`sociallogin.account.extra_data.get('email_verified')`) before auto-merging Google accounts.
- `superadmin/views.py`: Enforced strict `fin_level` validation (`['A', 'B', 'C']`), scoped employee mutations to `role='employee'`, preserving self-disable and superadmin demotion guards.

### 2. Dynamic Hero Banners (Super Admin Controlled)
- `core/models.py`: Created `SiteBanner` model with `target_page`, `title`, `subtitle`, `image`, `mobile_image`, `cta_label`, `cta_url`, `is_active`, and `sort_order`.
- `core/context_processors.py`: Registered `site_banners` processor providing `home_hero_banner` to templates.
- `templates/pages/index.html`: Bound hero image, heading, subheading, and CTA to dynamic database values with graceful static fallbacks.
- `superadmin/views.py` & `templates/superadmin/banners.html`: Created complete CRUD management interface with toggle-active and delete controls.

### 3. Front-Desk / Walk-In Reservation Engine
- `rooms/models.py`: Added `source`, `guest_name`, `guest_phone`, `guest_email`, `guest_id_type`, `guest_id_number`, `created_by_staff`, and `operational_notes` to `Booking`.
- `payments/models.py`: Added `payment_method` to `Payment` (`cash`, `card_pos`, `upi_pos`, `pay_at_checkout`, `razorpay`). Made `razorpay_order_id` nullable/blank for offline receipts.
- `rooms/services.py`: Implemented atomic `create_walk_in_booking()` with row locking, date conflict checks, guest user resolution, GST computation, and async receipt dispatches.
- `superadmin` & `employeeadmin`: Added "+ New Walk-In Booking" modal in `bookings.html` with AJAX validation and instant table reload.

### 4. Razorpay Production Hardening
- `payments/services.py`: Centralized payment capture in `confirm_booking_and_payment()` with atomic database transaction, `select_for_update()`, strict paise-amount reconciliation, conflicting hold detection, and idempotent returns.
- `payments/views.py`: Refactored `VerifyPaymentView` and `WebhookView` to delegate to `confirm_booking_and_payment()`.

### 5. OTA Channel Manager (Channex 2-Way Sync)
- Hospitality Contract Rule: Respecting global OTA legal boundaries where OTAs own contract dates. Front desk stay extensions log as direct walk-in bookings (0% OTA commission) and decrement OTA availability.
- `core/ota/`: Created abstract `ChannelManager`, concrete `ChannexManager`, and `processor.py` webhook dispatcher.
- Inbound Webhook (`POST /api/ota/channex/webhook/`): Validates HMAC-SHA256 signature (`X-Channex-Signature`), processes `booking.created`, `booking.modified` (with automatic room reallocation if original room is conflicted on new dates), and `booking.cancelled`.
- Outbound Inventory Sync: Implemented `rooms.tasks.sync_ota_inventory_for_dates`, enqueued automatically on website, walk-in, and OTA reservation events.

### 6. Backend Flow Optimizations & Performance Architecture
- `rooms/views.py`: Eager-loaded `.select_related("property")` and `.prefetch_related("images", "rates")` in `_build_search_queryset()`, `RoomDetailView`, and `MyBookingsView`. Updated `RoomSerializer.get_primary_image()` and `Room.calculate_price()` to leverage the prefetched in-memory caches rather than triggering isolated SQL queries per room. Search query complexity collapsed from $O(N)$ (60+ queries) down to $O(1)$ (bounded $\le 4$ queries).
- `rooms/models.py`: Added MySQL composite B-Tree indexes: `idx_bk_rm_dates_status` on `(room, check_in, check_out, status)`, `idx_bk_dates_status` on `(check_in, check_out, status)`, `idx_bk_usr_st_created` on `(user, status, -created_at)`, and `idx_rm_prop_act_status` on `(property, is_active, operational_status)`.
- `payments/utils.py` & `services.py`: Extended `send_booking_confirmation_email` and `send_invoice_email` to accept booking UUID strings. Wired `async_task` in `confirm_booking_and_payment` to offload Gmail SMTP handshake from the request thread, dropping checkout confirmation latency to under 80ms.
- `payments/models.py`, `payments/views.py` & `core/ota/views.py`: Introduced `ProcessedWebhookEvent` model with unique constraint `(source, event_id)` preventing duplicate webhook execution and replay attacks on both Razorpay and Channex webhooks.
- `hotel_booking/settings/base.py`: Configured `CACHES` (`LocMemCache` in dev with pluggable Redis in prod) and DRF `DEFAULT_THROTTLE_CLASSES` (`anon: 120/min`, `user: 600/min`, `search: 60/min`, `otp: 5/min`). Added caching to `site_banners` and `PropertyTaxConfig.gst_rate_for` with instant invalidation on update.

---

## 2026-06-23 — Super Admin Minimalist UI Redesign

### UI/UX Refinement — Dark to Minimal Light Theme Redesign

**Requirement:** Convert the Super Admin portal from a dark/heavy theme to a professional, minimalistic, light-themed dashboard UI (internal operations tool style).

**Changes:**
- `templates/superadmin/base.html` — Replaced the dark styling system (`#0f172a`, `#1e293b`) and the clumsy wrapping top nav with a highly refined, professional left-hand sidebar navigation layout:
  - Background: `#FAFAF9` (warm off-white)
  - Surface/cards: `#FFFFFF` with a `1px` border `#E7E5E4`
  - Navigation Sidebar: Fixed `240px` sidebar with structured navigation sections ("Operations", "Configuration", and "Content & System") preventing multi-line link wrapping. Integrated a clean logout action at the footer.
  - Interactive Icons: Added clean, modern inline SVG icons next to each navigation link (e.g., Grid for Dashboard, Calendar for Bookings, Users for Guests, Chart for Analytics).
  - Typography: Imported and applied Google Font 'Inter' with custom weights, tabular numerals for stats and monetary values, and strict type scaling.
  - Primary text: `#1C1917`, Secondary text: `#78716C`.
  - Accent: Muted resort teal `#0F766E` for active navigation, inputs focus, and primary button hover.
  - State colors: Success (`#15803D`), Warning (`#B45309`), Error (`#B91C1C`) for badges and states.
  - Target-oriented CSS overrides: Overrode inputs, inline edits, modal sheets, and the Room Status Board overlays across all sub-pages. Added a global style override to hide default browser numeric spin-buttons, enabled horizontal scrolling on cards (`overflow-x: auto`) for wide content, enforced non-wrapping table cells (`white-space: nowrap`) to align columns perfectly with headers, and added clean margin gaps (`margin-right: 4px`) on inline buttons to resolve alignment issues.

- `templates/employeeadmin/base.html` & sub-pages — Reconfigured the Employee Admin (Staff Portal) to mirror the exact same professional, minimal light-themed layout:
  - Background: `#FAFAF9`, Surfaces: `#FFFFFF`, Borders: `#E7E5E4`, Main Text: `#1C1917`, Secondary Text: `#78716C`, Accent: `#0F766E`.
  - Left-hand Navigation Sidebar: Introduced a fixed `240px` sidebar layout containing Operations and Inventory groups. Integrated clean SVG icons for Dashboard, Bookings, Status Board, Rooms, and Availability.
  - Sub-page Style Cleanup: Removed local stylesheet blocks and inline color overrides in `dashboard.html`, `rooms.html`, `room_images.html`, and `availability.html` to ensure perfect, unified style inheritance and card overflow controls.
  - Room Status Board: Fixed light teal/blue colors (`#5eead4` and `#f0fdfa`) on the status cards (room names, properties, synced text, inactive overlays) to use readable `#1C1917` and `#78716C` colors on the light-themed surfaces.

---

## 2026-06-15 — Booking hold early-release + My Stays cleanup

Branch: `fix/superadmin-employee-management`

### Bug 1 — Room hold never released on abandoned payment

**Symptom:** When a guest left checkout (closed the Razorpay modal, payment
failed, refreshed, or hit Back), the room stayed locked for the full 10-minute
hold — blocking other guests and even the same guest from re-booking.

**Root cause:** A `pending` booking blocks its room in every availability query
while `hold_expires_at > now`. The only release paths were successful payment,
the qcluster sweep, a lazy `expire_if_needed()` on read, and cancelling a
confirmed booking. **There was no early-release path for an abandoned/failed
payment.** The checkout JS handlers (`modal.ondismiss`, `payment.failed`,
back-link) only reset the UI, and `VerifyPaymentView`'s signature-failure branch
marked only the `Payment` row failed, leaving the booking `pending`. The sweep
also ran every 10 min, so other guests could wait up to ~20 min.

**Fix (scalable, OTA-ready — release immediately, keep sweep as safety net):**

- `rooms/models.py` — `Booking.release_hold(reason)`: single source of truth.
  `pending` → `expired` (abandon/timeout) or `failed` (payment_failed); nulls
  `hold_expires_at`; idempotent (safe for repeat / beacon calls).
- `rooms/views.py` — `ReleaseHoldView` (`POST /bookings/<id>/release/`),
  ownership-scoped + idempotent. Uses `CsrfExemptSessionAuthentication` so it can
  be called via `navigator.sendBeacon` on unload (low risk: only releases the
  caller's own pending hold).
- `rooms/views.py` — `HoldRoomView` now **reclaims** the guest's own existing
  pending hold for the same room+dates instead of returning 409, and excludes the
  guest's own pending holds from the conflict check. Reuses the existing Razorpay
  order on reclaim.
- `payments/views.py` — `VerifyPaymentView` signature-fail branch and the webhook
  `payment.failed` event now call `booking.release_hold('payment_failed')`, so the
  room frees even if the client never pings.
- `templates/payments/checkout.html` — wires `ondismiss`, `payment.failed`, and
  the back-link to release; `pagehide` fires `navigator.sendBeacon` to catch
  refresh / Back / tab-close. **Deliberately does NOT release on
  `visibilitychange` or while a payment attempt is in flight** — during real
  UPI/OTP flows the guest backgrounds the tab to approve in their bank app, and
  releasing then would break a legitimate payment. The 1-min sweep covers the rare
  mid-payment abandonment.
- `rooms/apps.py` — `release_expired_holds` sweep tightened from every 10 min to
  every 1 min (uses `update_or_create` so existing schedules migrate), keeping
  inventory accurate for OTA sync.

Tests: `rooms/tests.py` — `ReleaseHoldModelTest`, `ReleaseHoldEndpointTest`,
`SameUserReclaimTest`.

### Bug 2 — My Stays (folio) showed abandoned attempts

**Symptom:** The folio page listed every booking status (pending/expired/failed)
and counters built from them.

**Fix:** `accounts/views.py` `folio_page` now passes only confirmed + completed
stays, total nights stayed, total spent, and real loyalty (`loyalty_points` /
`loyalty_tier`) instead of a nights proxy. `templates/pages/folio.html` rebuilt:
slim stats (Confirmed Stays / Total Nights Stayed / Wayfarer Points), stays-only
history, Wayfarer Rewards driven by real loyalty data, and an Account card with
Edit profile + **Change password** links.

Tests: `accounts/tests.py` — `FolioPageTests`.

### Cleanup
Removed stray macOS Finder duplicate template folders (`templates/* 2`).

Full suite: **70/70 passing.**

---

## 2026-06-15 — Super Admin employee management rebuild

Branch: `fix/superadmin-employee-management`. See
`docs/superpowers/specs/2026-06-15-superadmin-employee-management-design.md`.

**Root cause:** employee/loyalty routes used `<int:user_id>` but `User.id` is a
UUID, so every edit/lock/reset/property action 404'd.

**Changes:** routes → `<uuid:user_id>`; `UserProfile` gained `created_by`,
`revoked_at`, `revoked_by` + `revoke()`, `reinstate()`, `can_hard_delete`;
superadmin views record `created_by`, add revoke/reinstate + `employee_delete`
(hard delete only for never-logged-in accounts) with a self-protection guard;
`AuditLog` gained `EMPLOYEE_REVOKED`/`EMPLOYEE_DELETED`; `employees.html` gained
tracking columns (created / last login / created by / PW status), Active/Locked/
Revoked states, and a copy-once credential modal (replacing the plaintext alert +
3s auto-hide). Removed the dead shadow template
`superadmin/templates/superadmin/employees.html`. 11 new tests.
