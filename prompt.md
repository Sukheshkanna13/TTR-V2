# Temple & Towns Resorts — Claude Code Business Logic Prompts
# Stack: Django 5 · PostgreSQL · django-q2 · Gunicorn · Tailwind + HTMX · Razorpay · Render

---

## CONTEXT (read before every session)

Multi-property boutique hotel booking platform.
Cities: Pondicherry, Auroville, Bengaluru.
Scale: <100 bookings/day · single Render web service + Postgres.
No Redis · No Celery · No WebSockets · Background tasks via django-q2 (DB-backed).
Loyalty tiers: SOJOURN → VOYAGER → PILGRIM.
Two admin roles: Employee Admin (assigned properties) · Super Admin (all properties).
Guest auth: Email OTP + Google OAuth via django-allauth — same email = merged profile.
Employee auth: Email + password only · no Google auth · 30-min auto-logout middleware.

---

## MODULE 1 — ROOM AVAILABILITY

**Prompt:**
Build `apps/bookings/services.py: get_available_rooms(property_id, check_in, check_out, guest_count)`.

Business rules:
- Return only rooms where no Booking with status IN ('CONFIRMED', 'HELD') overlaps the requested dates. Overlap condition: existing.check_in < requested check_out AND existing.check_out > requested check_in.
- Exclude rooms where status = 'MAINTENANCE' or is_active = False.
- Filter by guest_count <= room.capacity.
- Return queryset annotated with: nights count, total_price (nights × rate_per_night), display_status (from get_room_display_status()).
- No caching needed at this scale.

---

## MODULE 2 — BOOKING HOLD (DOUBLE-BOOKING PREVENTION)

**Prompt:**
Build `apps/bookings/services.py: create_booking_with_hold(guest, room_id, check_in, check_out)`.

Business rules:
- Wrap entire function in `transaction.atomic()`.
- Inside the transaction: `Room.objects.select_for_update().get(pk=room_id)` — this row-level lock blocks concurrent requests for the same room.
- Re-check availability inside the lock (same overlap query as Module 1). If conflict found: raise `ValidationError('Room not available for these dates')`.
- If clear: create Booking with status='HELD', hold_expires_at=now()+10 minutes, total_amount=calculated total.
- Immediately create a Razorpay order and store razorpay_order_id on the booking.
- Return the booking instance.

Scheduled task (runs every 10 minutes via django-q2):
- `release_expired_holds()`: set all HELD bookings where hold_expires_at < now() to EXPIRED. Room is then free for other guests.

---

## MODULE 3 — RAZORPAY PAYMENT + WEBHOOK

**Prompt:**
Build `apps/payments/views.py: razorpay_webhook(request)`.

Business rules:
- Extract `X-Razorpay-Signature` header. Verify HMAC signature using `settings.RAZORPAY_WEBHOOK_SECRET`. Reject with 400 if mismatch — never confirm a booking without this check.
- On `payment.captured` event: extract booking_id from `payload.payment.entity.notes.booking_id`.
- Inside `transaction.atomic()` with `select_for_update()`: if booking.status == 'HELD', set status='CONFIRMED', save razorpay_payment_id.
- Fire post-confirmation tasks via django-q2 `async_task()`:
  1. `tasks.generate_and_send_invoice(booking_pk)`
  2. `tasks.send_whatsapp_confirmation(booking_pk)`
  3. `tasks.award_loyalty_points(booking_pk)`
- Return 200 immediately — never do heavy work inside the webhook view.

---

## MODULE 4 — INVOICE & TAX ENGINE

**Prompt:**
Build `apps/payments/services.py: generate_invoice(booking_pk)`.

Business rules:
- Calculate: subtotal = room.rate_per_night × nights.
- Load `PropertyTaxConfig` for booking.property. Compare subtotal to config.threshold.
  - If subtotal > threshold: apply config.high_rate_pct (18%).
  - Else: apply config.low_rate_pct (5%).
- Create Invoice record: subtotal, tax_rate, tax_amount, total = subtotal + tax_amount.
- Render HTML invoice using template `emails/invoice.html`. Variables: booking, invoice, guest, property.
- Send via SendGrid using `django-anymail`. Subject: `Booking Confirmed — {property.name} · Ref #{booking.ref}`.
- Invoice template must include: booking ref, guest name + phone, property + room, check-in/out dates, nights count, rate/night, subtotal, tax line, total. Property logo + Super Admin customisable footer text.

---

## MODULE 5 — GUEST AUTHENTICATION (EMAIL OTP + GOOGLE OAUTH)

**Prompt:**
Build `apps/accounts/services.py: get_or_merge_user(email, name='', google_id='')`.

Business rules:
- `User.objects.get_or_create(email=email)` — email is the single unique key.
- If user already exists AND google_id provided AND profile.google_id is null: attach google_id to profile. This is the merge — one account, two login methods.
- Return (user, created_bool).

Email OTP flow:
- `send_otp(email)`: generate 6-digit OTP, store in Django cache with 5-min TTL key `otp:{email}`.
- `verify_otp(email, entered)`: fetch from cache, compare, delete on success, call `get_or_merge_user(email)`.

Google OAuth (django-allauth):
- Connect `social_account_added` signal. In handler: call `get_or_merge_user(email, google_id=uid)` and call `sociallogin.connect(request, user)` to link Google to the existing account if email matched.

---

## MODULE 6 — EMPLOYEE AUTHENTICATION + SESSION CONTROL

**Prompt:**
Build employee credential system and session auto-logout middleware.

Business rules:
- Super Admin creates employee via `create_employee(super_admin, email, temp_password, property_ids, fin_level)`.
  - Creates Django User with `is_staff=True`.
  - Creates `EmployeeAdmin` record: properties (M2M), fin_level (STATUS_ONLY / AMOUNTS_ONLY / FULL_FINANCIAL), created_by.
  - Sets `profile.must_change_password = True` — force change on first login.
- No Google OAuth for employees — email + password only.
- Super Admin can call `lock_employee(employee_pk)` and `reset_employee_password(employee_pk, new_password)` at any time.

Auto-logout middleware (`config/middleware.py: AutoLogoutMiddleware`):
- Check on every request: if user is authenticated AND has EmployeeAdmin record AND session has `last_activity`.
- If `now - last_activity > 1800` seconds: call `logout(request)`, redirect to `/admin/login/?reason=timeout`.
- Else: update `session['last_activity'] = time.time()`.

---

## MODULE 7 — FINANCIAL ACCESS CONTROL

**Prompt:**
Build `apps/bookings/serializers.py: get_booking_for_employee(booking, employee)`.

Business rules:
- Always include: id, guest name, room name, check_in, check_out, status, property name.
- If fin_level in ('AMOUNTS_ONLY', 'FULL_FINANCIAL'): include total_amount.
- If fin_level == 'FULL_FINANCIAL': include profit (call `get_profit(booking)`).
- Never include profit or amount for STATUS_ONLY — strip before response, not in DB.

Profit calculation `get_profit(booking)`:
- Query `RoomCost` for room + date range overlapping booking.check_in.
- If no cost record: return None (Super Admin has not set cost yet).
- profit = booking.total_amount - (cost.cost_per_night × nights).

---

## MODULE 8 — AVAILABILITY CALENDAR API

**Prompt:**
Build `GET /api/properties/{id}/calendar/?from=YYYY-MM-DD&to=YYYY-MM-DD`.

Business rules:
- Return all rooms for the property (active only).
- Return all bookings in the date window with status IN ('CONFIRMED', 'HELD', 'OTA_BLOCKED').
- Response shape: `{ rooms: [{id, name}], bookings: [{room_id, check_in, check_out, status, guest_name_or_null}] }`.
- Frontend colour map: CONFIRMED=red, HELD=yellow, OTA_BLOCKED=orange, free=green.
- Employee sees only rooms/bookings for their assigned properties. Super Admin sees all.

OTA blocking `block_ota_dates(employee, room, from_date, to_date, external_ref)`:
- Create Booking: status='OTA_BLOCKED', guest=None, total_amount=0, notes=f'OTA_REF:{external_ref}'.
- Room model needs `null=True, blank=True` on guest FK for this to work.
- Write AuditLog entry.

---

## MODULE 9 — LOYALTY POINTS ENGINE

**Prompt:**
Build `apps/loyalty/services.py: award_booking_points(booking_pk)` — called async via django-q2.

Business rules:
- Load `LoyaltyConfig` for booking.property (all values admin-configurable, never hardcoded).
- Determine base points:
  - Is this guest's first ever CONFIRMED booking? → use `config.first_booking_pts`.
  - Else → nights × config.pts_per_night.
- Monthly repeat check: if guest has ≥2 CONFIRMED bookings in same calendar month (including this one) → apply `config.monthly_repeat_multiplier`.
- Campaign check: query `CampaignRule` where is_active=True AND from_date ≤ booking.check_in ≤ to_date. Take highest multiplier found.
- Final = base × max(monthly_mult, campaign_mult). Write to `LoyaltyLedger(delta=+final, reason='BOOKING')`. Update `profile.loyalty_points`.
- Call `update_tier(user)`: find highest `LoyaltyTier` where min_pts ≤ profile.loyalty_points. If tier changed → async_task send tier upgrade email.

Cancellation points reversal:
- On booking CANCELLED: query LoyaltyLedger for all entries linked to this booking. Sum deltas. Write reversal entry (negative delta). Update profile balance.

---

## MODULE 10 — COUPON REDEMPTION

**Prompt:**
Build `apps/loyalty/services.py: redeem_for_coupon(user, coupon_rule_id)`.

Business rules:
- Load `CouponRule` (must be is_active=True).
- Check `profile.loyalty_points >= rule.points_required`. Raise ValidationError if insufficient.
- Generate unique code: `TT{int(rule.discount_amount)}OFF{uuid4().hex[:6].upper()}`.
- Create `UserCoupon`: user, code, discount_amount, expires_on = today + rule.expiry_days.
- Deduct points: write LoyaltyLedger(delta=-rule.points_required, reason='COUPON_REDEEM'). Update profile balance.
- Return code.

Apply coupon at checkout `apply_coupon(booking, code)`:
- Query UserCoupon: user=booking.guest, code=code, is_used=False, expires_on ≥ today.
- If valid: booking.discount_amount = coupon.discount_amount. booking.total_amount -= discount. Mark coupon is_used=True.
- If not found or expired: raise ValidationError.

---

## MODULE 11 — ROOM STATUS UX SIGNALS

**Prompt:**
Build `apps/bookings/services.py: get_room_display_status(room, check_in, check_out)`.

Business rules:
- If room.status == 'MAINTENANCE': return 'MAINTENANCE'.
- Count CONFIRMED + HELD bookings overlapping dates for this room.
- available = room.inventory_count - booked_count.
  - available <= 0 → 'SOLD_OUT'
  - available == 1 → 'LAST_ROOM'
  - available / room.inventory_count < 0.25 → 'LIMITED'
  - room.avg_rating >= 4.5 → 'TOP_RATED'
  - Else → 'AVAILABLE'

Status messages (Super Admin can override wording in admin panel):
- SOLD_OUT: "No rooms available for these dates"
- LAST_ROOM: "Only 1 room left — book now"
- LIMITED: "Only a few rooms remaining"
- TOP_RATED: "Recommended by our guests"
- MAINTENANCE: "Currently unavailable"

Alternative suggestions when SOLD_OUT:
- Query same property for rooms where `get_room_display_status` != 'SOLD_OUT', ordered by rate_per_night. Return top 3.

---

## MODULE 12 — AUDIT LOG

**Prompt:**
Build `apps/core/audit.py: audit(actor, action, obj, detail=None, request=None)`.

Business rules:
- Create `AuditLog`: actor=actor, action=action (string constant), entity_type=obj.__class__.__name__, entity_id=obj.pk, detail=detail or {}, ip from request.META if request provided, created_at=now().
- Index on (actor, created_at) and (entity_type, action) for fast dashboard queries.
- Call this from every admin action: booking confirm/cancel, employee create/lock, room edit, OTA block, coupon create, loyalty config change.

Dashboard aggregate queries for Super Admin:
- Revenue by day: `Booking.objects.filter(status='CONFIRMED', created_at__date=date).aggregate(Sum('total_amount'))`.
- Occupancy by property: confirmed bookings overlapping today / total rooms.
- Employee actions: `AuditLog.objects.filter(actor=emp).values('action').annotate(count=Count('id'))`.
- All filterable by date range, property, employee.

---

## MODULE 13 — VOLUNTEER & CAUSE MATCHING

**Prompt:**
Build `apps/csr/services.py: find_volunteer_matches(booking)`.

Business rules:
- Check if `BookingVolunteer` record exists for this booking. If not: return empty list.
- Query `BookingVolunteer` where:
  - program = same program as this booking's volunteer selection.
  - booking__property = same property.
  - booking__check_in < this booking's check_out AND booking__check_out > this booking's check_in (date overlap).
  - booking__status = 'CONFIRMED'.
  - Exclude this booking itself.
- Return with `select_related('booking__guest')` for display.
- Show matched guests to each other on the booking confirmation page.

Volunteer enrollment:
- Optional step during booking confirmation (after payment). Guest selects from active VolunteerPrograms. Creates `BookingVolunteer(booking, program)`.
- Super Admin can add/remove/toggle VolunteerPrograms from admin panel.

---

## MODULE 14 — SCHEDULED BACKGROUND TASKS (django-q2)

**Prompt:**
Configure `config/settings/base.py` Q_CLUSTER and `apps/tasks/scheduled.py`.

Task schedule:
- Every 10 minutes: `release_expired_holds()` — expire HELD bookings past hold_expires_at.
- Every hour: `notify_expiring_links()` — find HELD bookings expiring in <2 min, send WhatsApp reminder (for V2 payment link flow if re-introduced).
- Daily at 01:00: `auto_complete_bookings()` — set CONFIRMED bookings where check_out < today to COMPLETED, then call `award_completion_bonus(booking_pk)` for each.
- Daily at 01:00: `award_completion_bonus(booking_pk)` — credit config.completion_bonus points to guest, write LoyaltyLedger.

Q_CLUSTER config (no Redis — Postgres as broker):
```
Q_CLUSTER = {
    'name': 'temple_towns',
    'workers': 2,
    'timeout': 60,
    'retry': 120,
    'orm': 'default',
}
```

---

## MODEL REFERENCE (validated against codebase)

```
Booking: guest(FK User), room(FK Room), check_in, check_out, status
         (HELD/CONFIRMED/COMPLETED/EXPIRED/CANCELLED/OTA_BLOCKED),
         total_amount, discount_amount, hold_expires_at, razorpay_order_id,
         razorpay_payment_id, notes, created_at
         guest FK must be null=True, blank=True for OTA_BLOCKED rows

Room: property(FK), name, room_type, capacity, rate_per_night, description,
      amenities(JSON), status(ACTIVE/MAINTENANCE), inventory_count,
      avg_rating(computed), is_active

Property: city, name, address, description, cancellation_policy, is_active

PropertyTaxConfig: property(O2O), threshold, high_rate_pct, low_rate_pct

EmployeeAdmin: user(O2O), properties(M2M), fin_level, created_by, is_active

LoyaltyConfig: property(O2O), first_booking_pts, pts_per_night,
               completion_bonus, monthly_repeat_multiplier,
               referral_pts, review_pts

LoyaltyTier: name, min_pts, max_pts(nullable), discount_pct, priority_queue, sort_order

CampaignRule: name, multiplier, is_active, from_date, to_date

CouponRule: points_required, discount_amount, is_active, expiry_days

UserCoupon: user(FK), code, discount_amount, expires_on, is_used

LoyaltyLedger: user(FK), booking(FK nullable), delta(int), reason, created_at

RoomCost: room(FK), cost_per_night, from_date, to_date

AuditLog: actor(FK User nullable), action, entity_type, entity_id,
          detail(JSON), ip, created_at

Invoice: booking(O2O), subtotal, tax_rate, tax_amount, total, created_at

VolunteerProgram: name, description, is_active, created_by(FK)

BookingVolunteer: booking(O2O), program(FK nullable)

Attraction: city, name, category, description, address, opening_hrs,
            notes, is_visible, sort_order, created_by(FK)
```

---

## CONSTRAINTS (always apply)

- Never hardcode point values, tier thresholds, tax rates, or message strings — always load from DB config.
- Booking guest FK must allow null for OTA_BLOCKED rows — add to model definition.
- room.inventory_count field must be explicitly defined (not derived) — boutique hotels = 1 per room type.
- All admin actions must call `audit()` from apps/core/audit.py.
- Employee financial data always masked at serializer layer — database stores full data always.
- django-q2 async_task() for all post-payment work — never block the webhook response.
- Render deployment: 2 services only (web + postgres). No Redis, no separate worker process needed — qcluster runs inside the web dyno via `bin/render-start.sh`.