# TTR-V2 — Roadmap Sync (paste-ready for the Feature Roadmap sheet)

> **Generated:** 2026-06-13 · verified against branch `main` (`c3fa417`)
> **How to use:** Columns below match your Google Sheet exactly
> (`ID · Milestone · Version · Feature Area · Sprint · Est. Days · Priority · Status · Depends On · Notes`).
> The **Status** and **Notes** columns are the *corrected* values from code verification.
> Cells where status changed are marked **[CHANGED]** in Notes so you can spot them while updating.

---

## Full table (corrected)

| ID | Milestone | Version | Feature Area | Sprint | Est. Days | Priority | Status | Depends On | Notes |
|----|-----------|---------|--------------|--------|-----------|----------|--------|------------|-------|
| M01 | Static website live | V1 | Frontend | Sprint 0 | 3 | P0 | Done | - | HTML+Tailwind, Vercel deploy, WhatsApp CTA redirect |
| M02 | Brand design system | V1 | Design | Sprint 0 | 2 | P0 | Done | - | Navy #003D82, Blue #0071E3, typography, card tokens |
| M03 | City landing pages | V1 | Frontend | Sprint 0 | 2 | P1 | Done | M01 | Pondicherry / Auroville / Bengaluru static pages |
| M04 | WhatsApp booking CTA | V1 | UX | Sprint 0 | 1 | P0 | Done | M01 | Pre-filled WA message per property on every Book Now |
| M05 | Django project scaffold | V2 | Backend | Sprint 1 | 3 | P0 | Done | - | 7 local apps in INSTALLED_APPS (core/accounts/rooms/payments/superadmin/employeeadmin/loyalty) |
| M06 | Database models | V2 | Backend | Sprint 1 | 4 | P0 | Done | M05 | Booking, Room, Property, UserProfile, Loyalty*, Attraction, AuditLog |
| M07 | Design system → templates | V2 | Frontend | Sprint 1 | 3 | P0 | Done | M06 | base.html + components |
| M08 | Guest auth — Email OTP | V2 | Auth | Sprint 2 | 2 | P0 | Done | M06 | 6-digit OTP, otp_email.html template |
| M09 | Guest auth — Google OAuth | V2 | Auth | Sprint 2 | 1 | P0 | Done | M08 | **[CHANGED In Progress→Done]** merge via accounts/adapter.py pre_social_login→connect() |
| M10 | Employee auth — email+password | V2 | Auth | Sprint 2 | 2 | P0 | Done | M06 | **[CHANGED needs revision→Done]** folded into unified login flow |
| M11 | Super Admin auth + portal | V2 | Auth | Sprint 2 | 2 | P0 | Done | M10 | require_super_admin decorator |
| M12 | Role separation middleware | V2 | Auth | Sprint 2 | 1 | P0 | Done | M10 | **[CHANGED needs revision→Done]** accounts/middleware.py |
| M13 | UserProfile.role field | V2 | Auth | Sprint 2 | 1 | P0 | Done | M06 | **[CHANGED needs revision→Done]** ROLE_CHOICES + migration applied |
| M21 | Homepage — How It Works rewrite | V2 | UX | Sprint 2 | 1 | P1 | Done | - | **[CHANGED needs revision→Done]** in templates/pages/index.html |
| M22 | Search — city dropdown + validation | V2 | UX | Sprint 2 | 1 | P1 | Done | M06 | **[CHANGED needs revision→Done]** rooms/views.py + search.html |
| M23 | Guest Folio page | V2 | UX | Sprint 2 | 1 | P0 | Done | M06 | **[CHANGED Pending→Done]** accounts/views.py folio_page, nights in view |
| M24 | Edit Profile — wire to DB | V2 | UX | Sprint 2 | 2 | P1 | needs revision | M08 | **[CHANGED Pending→needs revision]** edit_profile_page exists; VERIFY email-change OTP + duplicate check |
| M25 | Global back navigation | V2 | UX | Sprint 2 | 1 | P2 | Done | - | **[CHANGED In Progress→Done]** components/_back_nav.html |
| M26 | Footer — location-aware redirects | V2 | UX | Sprint 2 | 1 | P2 | needs revision | - | VERIFY `?city=` param pre-selects in search view |
| M27 | Remove SSL/PCI claims | V2 | UX | Sprint 2 | 0.5 | P0 | Done | - | **[CHANGED Pending→Done]** zero `256-bit`/`PCI` matches in templates/ |
| M36 | Context processor — fix loop | V2 | Loyalty | Sprint 2 | 1 | P0 | needs revision | - | VERIFY is_authenticated guard + ≤2 queries |
| M41 | Trip Planner — WhatsApp CTA | V2 | Content | Sprint 2 | 0.5 | P1 | Done | - | wa.me pre-fill |
| M46 | Mobile: responsive nav + FAB | V2 | Mobile | Sprint 2 | 1 | P1 | Done | - | Hamburger nav, WA FAB |
| M14 | Room availability query | V2 | Booking | Sprint 3 | 2 | P0 | Done | M06 | overlap query, rooms/views.py |
| M15 | 10-min room hold | V2 | Booking | Sprint 3 | 2 | P0 | Done | M14 | select_for_update, hold_expires_at |
| M16 | Release expired holds task | V2 | Booking | Sprint 3 | 1 | P0 | Done | M15 | rooms/tasks.py release_expired_holds (+ auto_complete_bookings) |
| M17 | Razorpay webhook handler | V2 | Payments | Sprint 3 | 2 | P0 | Done | M15 | **[CHANGED Pending→Done]** payments/views.py webhook + HMAC verify |
| M18 | Invoice generation | V2 | Payments | Sprint 3 | 2 | P0 | Done | M17 | **[CHANGED Pending→Done]** compute_tax(), TT-{year}-{pk:05d} ref |
| M19 | Invoice email | V2 | Notifications | Sprint 3 | 1 | P1 | needs revision | M18 | **[CHANGED In Progress→needs revision]** works via Django send_mail; spec wanted SendGrid/anymail — decide if switch needed |
| M20 | WhatsApp booking confirmation | V2 | Notifications | Sprint 3 | 1 | P1 | Done | M17 | **[CHANGED Pending→Done]** core/tasks.send_whatsapp_message, async |
| M28 | Amenity icons — SVG not emoji | V2 | UX | Sprint 3 | 1 | P2 | needs revision | - | VERIFY amenity_icon templatetag exists |
| M34 | Loyalty points — award logic | V2 | Loyalty | Sprint 3 | 2 | P1 | Done | M17 | **[CHANGED Pending→Done]** loyalty/services.award_booking_points, wired in payments |
| M35 | Loyalty tier upgrade flow | V2 | Loyalty | Sprint 3 | 1 | P1 | needs revision | M34 | **[CHANGED Pending→needs revision]** _update_tier promotes silently — TO PLAN: add upgrade email |
| M39 | Things To Do — Attraction model | V2 | Content | Sprint 3 | 1 | P2 | Done | - | core/models.py Attraction + AttractionPhoto |
| M40 | Things To Do — guest page | V2 | Content | Sprint 3 | 2 | P2 | Done | M39 | **[CHANGED In Progress→Done]** core/views.explore_page + category filter |
| M42 | Mobile: full-bleed hero | V2 | Mobile | Sprint 3 | 1 | P1 | Pending | - | Not audited this pass — VERIFY |
| M43 | Mobile: search pill + bottom sheet | V2 | Mobile | Sprint 3 | 2 | P1 | Pending | - | Not audited this pass — VERIFY |
| M44 | Mobile: category scroll tabs | V2 | Mobile | Sprint 3 | 1 | P2 | Pending | - | Not audited this pass — VERIFY |
| M45 | Mobile: image-led property cards | V2 | Mobile | Sprint 3 | 1 | P2 | Pending | - | Not audited this pass — VERIFY |
| M29 | Employee Admin micro-app | V2 | Admin | Sprint 4 | 4 | P0 | Done | M10 | **[CHANGED Pending→Done]** employeeadmin/ app, 7 templates, live dashboard |
| M30 | Super Admin micro-app | V2 | Admin | Sprint 4 | 4 | P0 | Done | M11 | **[CHANGED Pending→Done]** superadmin/ app, 14 templates |
| M31 | Availability calendar API | V2 | Admin | Sprint 4 | 2 | P1 | Pending | M06 | GENUINE GAP — no /calendar/ endpoint. TO PLAN |
| M32 | Room management UI | V2 | Admin | Sprint 4 | 2 | P1 | needs revision | M29 | **[CHANGED Pending→needs revision]** CRUD + status board + images exist; VERIFY seasonal pricing + photo reorder |
| M33 | Financial masking | V2 | Admin | Sprint 4 | 1 | P0 | Done | M13 | **[CHANGED Pending→Done]** UserProfile.fin_level A/B/C enforced in employeeadmin |
| M37 | Coupon redemption | V2 | Loyalty | Sprint 4 | 2 | P2 | Pending | M34 | GENUINE GAP — no Coupon model / redeem / apply_coupon. TO PLAN |
| M38 | Loyalty admin config UI | V2 | Loyalty | Sprint 4 | 1 | P1 | Done | M30 | **[CHANGED Pending→Done]** superadmin/views.loyalty_config + template |
| M51 | Guest loyalty page (NEW) | V2 | Loyalty | Sprint 4 | 1 | P1 | Pending | M34 | NEW ROW — loyalty/views.py is empty stub; guests can't see points/tier. TO PLAN |
| M47 | OTA channel manager integration | V3 | OTA | Sprint 6 | 5 | P1 | Pending | M31 | Not started (expected) |
| M48 | Full loyalty — campaigns + advanced | V3 | Loyalty | Sprint 6 | 3 | P2 | Pending | M38 | Not started (expected) |
| M49 | Volunteer / Travel for a Cause | V3 | CSR | Sprint 6 | 3 | P2 | Pending | M39 | Not started (expected) |
| M50 | Analytics dashboard | V3 | Analytics | Sprint 6 | 4 | P2 | Pending | M30 | Not started (expected) |

---

## Changes to plan (the only open V2 work)

These are the rows above that still need real work. Ordered by recommended sequence:

| # | Row(s) | What to build | Priority | Est. |
|---|--------|---------------|----------|------|
| 1 | M51 (new) | Guest-facing loyalty page: points balance, tier, progress to next tier. Fill the empty `loyalty/views.py`. | P1 | ~1d |
| 2 | M35 | Tier-upgrade email — fire notification when `_update_tier` promotes a guest. | P1 | ~0.5d |
| 3 | M31 | Availability calendar API — `GET /api/properties/{id}/calendar/` JSON for admin timeline. | P1 | ~2d |
| 4 | M37 | Coupon redemption — `Coupon` model + `redeem_for_coupon()` + `apply_coupon()` at checkout. | P2 | ~2d |
| 5 | M24, M26, M28, M32, M36, M42–M45 | Depth-audit / VERIFY items — confirm in one QA pass; rebuild only if broken. | mixed | ~1d QA |

## Status legend changes summary
- **20 milestones** moved up to **Done** from a worse status (Pending / In Progress / needs revision).
- **4 milestones** set to **needs revision** (exist but need a fix or a decision): M19, M24, M32, M35.
- **2 genuine gaps** remain Pending: M31, M37 — plus **1 new row** M51.
- **6 items** flagged VERIFY (not audited): M26, M28, M36, M42, M43, M44, M45.
