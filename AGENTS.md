# Temple and Towns Resorts — Codex Cheat Sheet

> **Project:** TTR-V2 · Django 6 monolith · hotel booking platform  
> **Properties:** Pondicherry · Auroville · Bengaluru  
> **Roadmap stage:** V2 in development (V1 shipped)

---

## Quick Orientation

```
manage.py               Django entry point
hotel_booking/          Project package (settings, root urls, wsgi/asgi)
  settings/
    base.py             Shared settings for all environments
    dev.py              Local dev overrides (DEBUG=True, CORS open)
    prod.py             Production overrides
accounts/               Auth — email OTP + Google OAuth, custom user model
rooms/                  Room inventory, availability, 10-min hold logic
payments/               Razorpay integration, booking confirmation
core/                   Shared utilities, background task hooks
templates/              Django SSR HTML templates
static/                 CSS, JS, images
```

Architecture is **Django MVT** — Models own business logic, Views handle requests only, Templates own presentation. URL files route only; no view logic in `urls.py`.

---

## Setup

```bash
# 1. Install production dependencies
pip install -r requirements.txt

# 2. Install dev tools (code-review-graph, linters, etc.)
pip install -r requirements-dev.txt

# 3. Copy and fill environment variables
cp .env.example .env          # set SECRET_KEY, RAZORPAY keys, DB URL, etc.

# 4. Run migrations
python manage.py migrate

# 5. Start dev server
python manage.py runserver

# 6. Start background task worker (separate terminal)
python manage.py qcluster
```

---

## Environment Variables (`.env`)

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` in dev, `False` in prod |
| `ALLOWED_HOSTS` | Comma-separated hostnames |
| `DATABASE_URL` | PostgreSQL URL for prod; omit for SQLite in dev |
| `RAZORPAY_KEY_ID` | Razorpay public key |
| `RAZORPAY_KEY_SECRET` | Razorpay secret key — never commit |
| `EMAIL_HOST_USER` | Gmail SMTP sender address |
| `EMAIL_HOST_PASSWORD` | Gmail app password |

---

## Apps and Responsibilities

### `accounts`
Custom user model. Authentication via:
- Email + OTP (one-time verification code)
- Google OAuth via `django-allauth`

If a guest uses both methods with the same email, the system merges them into one account. Auth middleware lives in `middleware.py`; custom permissions in `permissions.py`.

### `rooms`
Room inventory per property. Key logic:
- **10-minute hold** — when a guest confirms room selection, the room is locked for that guest for 10 minutes. If payment is not completed, the hold expires automatically via a background task (`tasks.py`).
- `models.py` owns `expire_if_needed()` and availability checks — keep business logic here, not in views.
- Booking status states: `HELD` → `CONFIRMED` → `COMPLETED` / `EXPIRED` / `CANCELLED`

### `payments`
Razorpay payment gateway integration. HMAC-SHA256 signature verification on every callback. Card data is never stored — only order IDs and payment references. On success: booking status updated, invoice email sent, WhatsApp confirmation triggered, loyalty points credited.

### `core`
Shared utilities and background task hooks. Background tasks run via `django-q2` (`qcluster` worker). Always run the worker alongside the dev server when testing hold expiry, email delivery, or post-booking flows.

---

## Key Commands

```bash
python manage.py runserver          # dev server on :8000
python manage.py qcluster           # background worker (required for holds + email)
python manage.py migrate            # apply migrations
python manage.py makemigrations     # generate new migrations
python manage.py createsuperuser    # create Super Admin account
python manage.py collectstatic      # gather static files for prod
```

Production is served via Gunicorn (`Procfile`):
```
web:    gunicorn hotel_booking.wsgi --log-file -
worker: python manage.py qcluster
```

---

## Development Tooling (`requirements-dev.txt`)

Dev dependencies are intentionally separate from production. Install with `pip install -r requirements-dev.txt`.

| Package | Purpose |
|---------|---------|
| `code-review-graph>=2.3.3` | Code review visualisation and analysis — maps review coverage, surfaces complex areas, helps prioritise PR attention |

To add more dev tools (linters, test runners, etc.) append them to `requirements-dev.txt`. Never add dev-only packages to `requirements.txt`.

---

## Roadmap

| Version | Status | Goal |
|---------|--------|------|
| **V1** | Shipped | Property showcase website + WhatsApp booking enquiry |
| **V2** | In development | Online booking, payments, guest accounts, loyalty start, admin panels |
| **V3** | Planned | OTA sync, full loyalty campaigns, Room UX signals, analytics |

### V2 Feature Checklist
- [x] Room search and real-time availability
- [x] 10-minute room hold (double-booking prevention)
- [x] Razorpay payment integration (UPI, cards, net banking, wallets)
- [x] Guest accounts — email OTP + Google OAuth
- [x] Auto invoice by email + WhatsApp on confirmation
- [x] Employee admin panel (room management, availability calendar, bookings)
- [x] Super Admin panel (platform-wide control, financials, employee management)
- [ ] Loyalty points program (earn per stay, 3 tiers, coupon redemption)

---

## Architecture Rules to Follow

- **No view logic in `urls.py`** — routes only. Views live in `views.py`.
- **Business logic belongs in models** — `expire_if_needed()`, availability checks, point calculations go in `models.py` or `utils.py`, not views.
- **Views stay thin** — request handling and orchestration only; delegate to models and serializers.
- **Settings are split** — always import from `hotel_booking.settings.dev` or `.prod`, never directly from `base`.
- **Background tasks via django-q** — do not use `threading` or `celery`; the stack uses `django-q2`.
- **Payments are verified server-side** — never trust client-side payment confirmation; always verify HMAC signature from Razorpay callback.

---

## Admin Access

| Role | What They Control |
|------|-------------------|
| **Employee Admin** | Rooms, availability calendar, bookings for assigned properties only |
| **Super Admin** | Everything — all properties, employees, financials, loyalty program, analytics |

Guest login and admin login are completely separate systems with separate access paths.

---

## Loyalty Program (V2)

Points are earned on: first booking, per night stayed, repeat bookings (higher rate), monthly repeat (multiplier), reviews, referrals. Three tiers (Base → Mid → Top) with configurable names, thresholds, and discounts set by Super Admin. Guests redeem points for discount coupons. All rules are runtime-configurable — nothing is hardcoded.

---

## Change Log

Significant changes by AI sessions are logged in [`docs/AGENT-CHANGELOG.md`](docs/AGENT-CHANGELOG.md)
(newest first), with root cause + what changed for each fix. Read it before
touching booking holds, the checkout flow, or the folio / employee-management
pages.

**Booking hold lifecycle (read before editing checkout):** holds release the
instant a guest abandons checkout via `POST /bookings/<id>/release/`
(`Booking.release_hold()`), wired in `checkout.html` to modal-dismiss /
payment-failure / back-nav / `pagehide` (sendBeacon). Payment-failure paths
release server-side too. The qcluster sweep (`release_expired_holds`, every 1 min)
is only a safety net. Do **not** release on `visibilitychange` — it breaks
UPI/OTP flows where the guest backgrounds the tab to approve payment.
