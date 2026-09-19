# Agent Change Log

A running record of changes made by AI coding sessions, newest first. Each entry
lists the problem, the root cause, and what changed, so future sessions have
context without re-deriving it.

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
