# Temple & Towns — V2 Sprint · Claude Code Prompt

## STEP 0 — READ FIRST (mandatory before any code)
```
1. Read CLAUDE.md
2. Read docs/DESIGN_SYSTEM.md
3. Read docs/CELERY_TO_DJANGO_Q_MIGRATION.md
4. Read TT_ClaudeCode_Prompts.md
5. git log --oneline -20
6. python manage.py graph_models --all -o graph.png
7. grep -r "TODO\|FIXME" apps/ --include="*.py"
```

## STACK (never change)
Django 5 · PostgreSQL · django-q2 · Gunicorn · Tailwind+HTMX · Razorpay · Render
No Redis · No Celery · No WebSockets · Single Postgres DB

---

## FIX 1 — Homepage "How It Works"
Remove all approval/pending language. Rewrite 4 steps:
1. Dream it — Browse properties across Pondicherry, Auroville & Bengaluru
2. Pick your stay — Choose room, dates, guests
3. Secure it — Room held 10 min while you pay, no one else can take it
4. Relax — Confirmed, invoice in inbox, WhatsApp sent

Tone: warm concierge. No backend operational language. Inline SVG icons, no emoji.

---

## FIX 2 — Separate Admin / Guest Auth
- Guest login: `/accounts/login/` (allauth, guests only)
- Employee login: `/admin-portal/login/` (separate view + template)
- Super Admin login: `/super-admin/login/` (separate view + template)
- Add `UserProfile.role` field: choices = GUEST / EMPLOYEE / SUPER_ADMIN
- Middleware: `is_staff` user hitting `/accounts/login/` → redirect to `/admin-portal/login/`
- Guest hitting `/admin-portal/` → redirect to `/accounts/login/`
- Header: small "Staff login" link only, not in guest nav
- Auth checks use `role` field + permission groups, not `is_superuser` alone

---

## FIX 3 — Guest Folio: Fix Broken Variables
Find `num_nights`, `pluralize`, "30 May 2026" in templates. Fix every broken `{{ }}`:
- Pass from view: `nights = (booking.check_out - booking.check_in).days`
- Ensure: `booking.guests_count`, `booking.room.name`, `booking.total_amount` all in context
- Guard: `if booking.guest != request.user: return 403`

---

## FIX 4 — Edit Profile: Wire to DB
Fields: name + phone → save immediately. Email → OTP verification required.

Email change flow:
1. Send OTP to NEW email (6-digit, 10-min TTL, cache key: `email_change:{user.pk}:{new_email}`)
2. Verify OTP → update `user.email`, clear cache
3. Validate: email not already taken, phone = 10-digit Indian format, name non-empty

---

## FIX 5 — Loyalty Points: Fix Loop + Wire Logic
Context processor guard (first line): `if not request.user.is_authenticated: return {}`
Wrap entire processor in `try/except Exception: return {}`

Award logic in `apps/loyalty/services.py: award_booking_points(booking_pk)`:
```
1. Load LoyaltyConfig for booking.property (never hardcode values)
2. First ever CONFIRMED booking? → base = config.first_booking_pts
   Else → base = nights × config.pts_per_night
3. ≥2 bookings this calendar month? → apply config.monthly_repeat_multiplier
4. Active CampaignRule covering check_in date? → take highest multiplier
5. final = base × multiplier
6. Write LoyaltyLedger(delta=+final, reason='BOOKING_CONFIRMED')
7. Update profile.loyalty_points
8. update_tier(user): find tier where min_pts ≤ points, update if changed, send upgrade email
```

Context processor exposes: `loyalty_points`, `loyalty_tier`, `loyalty_tier_next`, `loyalty_progress_pct`

---

## FIX 6 — Admin Panels: Two Separate Micro-Apps

Create `apps/superadmin/` and `apps/employeeadmin/`. Each gets `urls.py`, `views.py`, `decorators.py`, `templates/{app}/`.

**Decorators:** `@require_super_admin` · `@require_employee_admin` — redirect to respective login if wrong role.

**Nav rendered by role** (context processor → `user_role`):
- Guest → guest nav only
- Employee → employee nav only
- Super Admin → super admin nav only

**Super Admin views:**

| URL | View | Key data |
|---|---|---|
| `/super-admin/dashboard/` | Dashboard | Revenue today/month, active bookings, occupancy % |
| `/super-admin/employees/` | Employee CRUD | Create: email+temp_password+properties+fin_level. Edit/lock/reset. Write AuditLog. |
| `/super-admin/loyalty/` | Loyalty config | LoyaltyConfig per property, LoyaltyTier CRUD, CampaignRule CRUD, CouponRule CRUD |
| `/super-admin/tax/` | Tax config | PropertyTaxConfig: threshold, high_rate_pct, low_rate_pct |
| `/super-admin/analytics/` | Analytics | Revenue by property/date, occupancy trends |
| `/super-admin/audit/` | Audit log | AuditLog table, filterable by actor/date/action |

**Employee Admin views** (all filtered to `request.user.employeeadmin.properties.all()`):

| URL | View | Key data |
|---|---|---|
| `/admin-portal/dashboard/` | Dashboard | Active guests, occupancy, upcoming checkouts |
| `/admin-portal/rooms/` | Room CRUD | Add/edit rooms, photos (ImageField+sort_order), seasonal pricing |
| `/admin-portal/calendar/` | Availability | JSON API + React calendar. OTA block: date range + ref → OTA_BLOCKED record (guest=null) |
| `/admin-portal/bookings/` | Bookings list | Confirmed/completed/cancelled. Amount masked by fin_level. |

Financial masking at view/template level:
- STATUS_ONLY → hide amount, profit
- AMOUNTS_ONLY → show amount, hide profit
- FULL_FINANCIAL → show all

---

## FIX 7 — Footer Location Links
Change: `/stays/` → `/stays/?city=Pondicherry`
Search view: `city = request.GET.get('city')` → pre-filter properties, pre-select dropdown.

---

## FIX 8 — Things To Do: Attraction Model + Page
```python
class Attraction(models.Model):
    city, name, category (TEMPLE/BEACH/MUSEUM/RESTAURANT/SHOPPING/NATURE/EVENT)
    description, address, opening_hrs, notes
    is_visible=True, sort_order=0, created_by FK
# AttractionPhoto: FK Attraction, ImageField, is_primary, sort_order
```
Guest page `/explore/`: cards with photo + name + category badge + description + hours. Category filter tabs.
Admin control in both portals: add/edit/hide/photo upload.

---

## FIX 9 — Trip Planner → WhatsApp CTA
Rename to **"Plan with an Expert"**. On click:
```
wa.me/91{settings.BRAND['whatsapp_number']}?text=Hi! I'd love help planning my perfect Pondicherry getaway. Could you craft a personalised itinerary for me?
```
Open `target="_blank" rel="noopener"`. Secondary outlined button style (design system tokens).

---

## FIX 10 — Search: Predefined Dropdown
Replace city text input with `<select>` from `Property.objects.filter(is_active=True).values_list('city',flat=True).distinct()`.
Guest count: +/− stepper, min=1 max=10.
Date validation: check_in ≥ today, check_out > check_in (JS + server-side).
Submit: `GET /search/?city=X&check_in=Y&check_out=Z&guests=N`

---

## FIX 11 — Payment Page: Remove Security Claims
Delete all text: "256-bit", "SSL encryption", "PCI-DSS", "PCI DSS", "compliant".
Replace with: `"Payments are processed securely. Your card details are never stored."`

---

## FIX 12 — Global Back Navigation
Create `templates/components/_back_nav.html`:
```html
<a href="{{ back_url }}" class="text-sm text-tt-blue-500 hover:underline">← {{ back_label|default:"Go back" }}</a>
```
Include at top of every non-homepage template. Each view passes `back_url` + optional `back_label`.
Payment page back: warn that hold will be released if they navigate away.

---

## FIX 13 — Amenity Icons: SVG not Emoji
Create `templatetags/tt_filters.py: amenity_icon` filter.
Map keys (`wifi`, `ac`, `pool`, `parking`, `breakfast`, `hot_water`, `tv`, `balcony`, `sea_view`, `garden_view`) to 20×20 inline SVGs from Tabler Icons (MIT). Use `currentColor`, `aria-label`. Mark safe.
Room amenities stored as JSON array of keys. Remove all emoji from templates.

---

## FIX 14 — Mobile Responsive
- Nav: hamburger menu <768px, collapse to drawer
- Cards: 1-col mobile, 2-col tablet, 3-col desktop
- Booking widget: sticky bottom bar on mobile (price + "Book now")
- Date pickers: `<input type="date">` on mobile
- Min tap target: 44×44px. Min body font: 16px.
- Test at: 375px / 390px / 414px
- Verify `<meta name="viewport" content="width=device-width, initial-scale=1">` in base.html

---

## FIX 15 — Post-Payment Pipeline
Razorpay webhook (`payment.captured`) → verify signature → set booking CONFIRMED → fire 3 async tasks:

**Task 1 — Invoice:**
- subtotal = nights × rate. Tax from PropertyTaxConfig (threshold check). total = subtotal + tax.
- Booking ref: `TT-{year}-{booking.pk:05d}`
- Render `templates/emails/invoice.html` (ref, guest name+phone, property, room, dates, nights, rate, subtotal, tax, total)
- Send via django-anymail subject: `Your booking is confirmed — {property.name}`

**Task 2 — WhatsApp:**
```
Hi {name}! Your stay at {property} is confirmed.
Ref: {ref} · {check_in} to {check_out} · {nights} nights
Invoice sent to {email}. See you soon!
```
Number from `settings.BRAND['whatsapp_number']`

**Task 3 — Loyalty points:** call `award_booking_points(booking_pk)` from Fix 5.

**Test mode:** Use Razorpay test keys in `.env`. Test card: `4111 1111 1111 1111`. Use ngrok for local webhook testing.

---

## COMMIT FORMAT
`fix(N): description` — one commit per fix.

## NEVER
- Add Redis, Celery, second DB, or new infrastructure
- Hardcode points, tier names, tax rates, or phone numbers
- Add SSL/PCI-DSS claims
- Modify `requirements.txt` without flagging it

