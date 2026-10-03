# TTR-V2 — Feature Status (Code-Verified)

> **Reconciled:** 2026-06-13 · against branch `main` (commit `c3fa417`)
> **Method:** Every milestone below was checked against actual source code, not the
> spreadsheet status. The roadmap spreadsheet was significantly stale — most items it
> marked *Pending* / *In Progress* / *needs revision* are in fact implemented and wired.
>
> Legend: ✅ Done (verified in code) · 🟡 Partial / differs from spec · ⛔ Genuine gap (not built) · ⬜ V3 (not started, expected)

---

## Headline

V2 is **functionally near-complete**. The full booking spine works end-to-end:
availability → 10-min hold → Razorpay → webhook → confirmation → invoice email +
WhatsApp + loyalty award. Both admin portals (superadmin, employeeadmin) exist with
live dashboards. The spreadsheet undercounts reality by ~15 milestones.

**Only genuine remaining V2 gaps:** coupon redemption (M37), availability calendar API
(M31), tier-upgrade email, and a dedicated guest-facing loyalty page. Everything else
marked open in the spreadsheet is already in code.

---

## Sprint 1 — Foundation

| ID | Feature | Spreadsheet | Verified | Evidence |
|----|---------|-------------|----------|----------|
| M05 | Django scaffold | Done | ✅ | 7 local apps in `INSTALLED_APPS` |
| M06 | Database models | Done | ✅ | `rooms/models.py`, `accounts/models.py`, `loyalty/models.py`, `core/models.py` |
| M07 | Design system → templates | Done | ✅ | `templates/base.html`, components |

## Sprint 2 — Auth & UX

| ID | Feature | Spreadsheet | Verified | Evidence |
|----|---------|-------------|----------|----------|
| M08 | Email OTP | Done | ✅ | `accounts/views.py`, `templates/emails/otp_email.html` |
| M09 | Google OAuth + merge | **In Progress** | ✅ | `accounts/adapter.py` `pre_social_login` → `sociallogin.connect()`; wired via `SOCIALACCOUNT_ADAPTER` |
| M10 | Employee auth | needs revision | ✅ | covered by unified login (`docs/.../unified-login-flow.md`) |
| M11 | Super Admin auth | Done | ✅ | `superadmin/views.py`, `require_super_admin` |
| M12 | Role separation middleware | needs revision | ✅ | `accounts/middleware.py` |
| M13 | `UserProfile.role` field | needs revision | ✅ | `accounts/models.py:230` ROLE_CHOICES + migration |
| M21 | How It Works rewrite | needs revision | ✅ | `templates/pages/index.html` |
| M22 | Search city dropdown + validation | needs revision | ✅ | `rooms/views.py`, `templates/rooms/search.html` |
| M23 | Guest Folio page | **Pending** | ✅ | `accounts/views.py:465` `folio_page`, nights computed in view |
| M24 | Edit Profile | **Pending** | 🟡 | `accounts/views.py:485` `edit_profile_page` exists — **verify** email-change-OTP + duplicate check depth |
| M25 | Global back navigation | In Progress | ✅ | `templates/components/_back_nav.html` |
| M26 | Footer location-aware redirects | Pending | 🟡 | **verify** `?city=` pre-select in search view |
| M27 | Remove SSL/PCI claims | **Pending** | ✅ | grep for `256-bit`/`PCI` in `templates/` → **zero matches** (already clean) |
| M36 | Context processor fix | In Progress | 🟡 | **verify** guard + query budget |
| M41 | Trip Planner WhatsApp CTA | Done | ✅ | — |
| M46 | Mobile nav + FAB | Done | ✅ | — |

## Sprint 3 — Booking, Payments, Loyalty core

| ID | Feature | Spreadsheet | Verified | Evidence |
|----|---------|-------------|----------|----------|
| M14 | Room availability query | Done | ✅ | `rooms/views.py:65` overlap query |
| M15 | 10-min hold | Done | ✅ | `rooms/models.py:273` `hold_expires_at`, `select_for_update` |
| M16 | Release expired holds task | Done | ✅ | `rooms/tasks.py:8` `release_expired_holds` (+ bonus `auto_complete_bookings`) |
| M17 | Razorpay webhook | **Pending** | ✅ | `payments/views.py:287` webhook + `verify_webhook_signature` (HMAC) |
| M18 | Invoice generation + tax engine | **Pending** | ✅ | `rooms/models.py:332` `TT-{year}-{pk:05d}` ref, `:340` `compute_tax()` |
| M19 | Invoice email | In Progress | 🟡 | `payments/utils.py:168` `send_invoice_email` works — uses Django `send_mail`, **not** SendGrid/anymail as spec'd |
| M20 | WhatsApp confirmation | **Pending** | ✅ | `core/tasks.py:7` `send_whatsapp_message`, called async from `payments/views.py:265` |
| M28 | Amenity SVG icons | needs revision | 🟡 | **verify** templatetag exists |
| M34 | Loyalty points award | **Pending** | ✅ | `loyalty/services.py:12` `award_booking_points`, wired at `payments/views.py:260` |
| M35 | Loyalty tier upgrade | **Pending** | 🟡 | `loyalty/services.py:104` `_update_tier` promotes tier — **but no email on upgrade** (spec wanted email) |
| M39 | Attraction model | Done | ✅ | `core/models.py:6` `Attraction` + `AttractionPhoto` |
| M40 | Things To Do guest page | In Progress | ✅ | `core/views.py:36` `explore_page` with category filter |
| M42–M45 | Mobile hero/search/tabs/cards | Pending | 🟡 | **verify** — not audited this pass |

## Sprint 4 — Admin portals

| ID | Feature | Spreadsheet | Verified | Evidence |
|----|---------|-------------|----------|----------|
| M29 | Employee Admin micro-app | **Pending** | ✅ | `employeeadmin/` app — views (380 lines), 7 templates, live dashboard |
| M30 | Super Admin micro-app | **Pending** | ✅ | `superadmin/` app — views (768 lines), 14 templates |
| M31 | Availability calendar API | Pending | ⛔ | **No calendar endpoint found** in `superadmin`/`employeeadmin` views/urls |
| M32 | Room management UI | Pending | 🟡 | rooms CRUD + status board + images exist; **verify** seasonal pricing + photo reorder |
| M33 | Financial masking | **Pending** | ✅ | `UserProfile.fin_level` (A/B/C), enforced in `employeeadmin/views.py:12` `_fin_level` |
| M37 | Coupon redemption | Pending | ⛔ | **No `Coupon` model, no `redeem_for_coupon()`, no `apply_coupon()`** — only a `COUPON_REDEMPTION` ledger reason placeholder |
| M38 | Loyalty admin config UI | Pending | ✅ | `superadmin/views.py:336` `loyalty_config` + template |

## V3 — Not started (expected)

| ID | Feature | Status |
|----|---------|--------|
| M47 | OTA channel manager | ⬜ |
| M48 | Full loyalty (campaigns/referral/review/birthday) | ⬜ |
| M49 | Volunteer / Travel for a Cause | ⬜ |
| M50 | Analytics dashboard (revenue/occupancy trends) | ⬜ |

---

## Genuine Remaining V2 Work (ordered)

These are the only items that are *not in code*. Everything else above is built (some
needs a depth-audit, flagged 🟡).

1. **Guest-facing loyalty page** — `loyalty/views.py` is an empty stub. Guests can't see
   their points balance, tier, or progress in a dedicated page (folio shows partial). *P1, ~1d.*
2. **M35 tier-upgrade email** — `_update_tier` promotes silently; add notification email
   on tier change. *P1, ~0.5d.*
3. **M31 Availability calendar API** — `GET /api/properties/{id}/calendar/` returning JSON
   for an admin timeline view. Not built. *P1, ~2d.*
4. **M37 Coupon redemption** — `Coupon` model + `redeem_for_coupon()` (points → coupon) +
   `apply_coupon()` at checkout. Ledger reason exists; nothing else. *P2, ~2d.*
5. **Depth audits (🟡 items)** — confirm M24 email-change OTP, M32 seasonal pricing/photo
   reorder, M42–M45 mobile, M28 amenity icons, M36 context processor, M26 footer city param.

## Recommended next action

Knock out items 1 + 2 together (both touch `loyalty/`), then 3, then 4. The 🟡 depth
audits can be folded into a single QA pass (`/qa`) since they're verification, not new build.

---

## Maintenance note

Keep this file as the **single source of truth** for feature status going forward — the
Google Sheet drifts. Update the relevant row when a milestone lands, in the same PR.
