# Temple and Towns Resorts (TTR) — V2

A comprehensive, real-time Django 6 monolithic hotel booking platform managing multiple properties (Pondicherry, Auroville, Bengaluru). The system handles guest reservations, dynamic pricing, real-time room holds, staff operational dashboards, and superadmin full-platform controls.

---

## 🚀 Tech Stack & Architecture

- **Core Framework**: Django 6 (MVT Architecture)
- **Database**: MySQL (Primary) / PostgreSQL (Production) / SQLite (Fallback)
- **Background Tasks**: `django-q2` (critical for hold-expirations and emails)
- **Payments**: Razorpay (with strict server-side HMAC-SHA256 signature verification)
- **Frontend**: Django Templates, Vanilla JS (AJAX Polling for real-time dashboards), Chart.js, HTML/CSS (No heavy JS frameworks)
- **Authentication**: Custom User Model, Email OTP (stored in DB), Google OAuth

---

## ✨ Key Real-Time & Core Features

### 1. 10-Minute Reservation Hold Engine
To completely prevent double-booking, the system employs a real-time lock on inventory.
- When a guest selects a room, a `pending` booking is created with a `hold_expires_at` timestamp.
- A background `django-q2` worker constantly evaluates holds. If payment is not completed and verified within 10 minutes, the lock is automatically released and the inventory is restored.
- **Visuals**: Staff and Superadmin dashboards feature live JavaScript countdown timers that turn amber (< 5 mins) and red (< 2 mins) before automatically dropping off the board.

### 2. 3-Step Secure Registration (No Ghost Users)
Prevents database bloating from abandoned sign-ups:
1. **Initiate**: Stores name, email, and phone in a temporary `PendingRegistration` table. Sends an OTP.
2. **Verify**: User inputs OTP, validating the email.
3. **Finalize**: User sets a password. Only then is the primary `User` record written to the database.

### 3. Server-Verified Razorpay Payments
- **Zero Client-Side Trust**: Client-side payment confirmations are never trusted to finalize a booking.
- **HMAC Verification**: Every Razorpay callback and webhook must pass HMAC signature validation before a room is marked `confirmed`.
- **Automated Triggers**: Upon confirmation, the system auto-generates a booking reference (`TT-YYYY-XXXXX`), computes dynamic tax thresholds, issues loyalty points, and dispatches an invoice email & WhatsApp alert.

### 4. Real-Time Polling Dashboards
- Both the **Superadmin** and **Staff** portals feature operational dashboards that auto-refresh via AJAX (every 30 seconds).
- Core KPIs (Active Stays, Today's Check-ins, Today's Checkouts, Revenue) update seamlessly without requiring page reloads.

---

## 📊 Project Status (V2)

V2 is **functionally near-complete**. The full booking spine works end-to-end:
availability → 10-minute hold → Razorpay → webhook (HMAC) → confirmation → invoice email
+ WhatsApp + loyalty award. Both operational portals (Super Admin, Staff) ship with live
polling dashboards.

> **Single source of truth for feature status:** [`docs/FEATURE-STATUS.md`](docs/FEATURE-STATUS.md)
> (code-verified). The Google Sheet roadmap drifts — update FEATURE-STATUS.md in the same PR
> as each feature lands. Paste-ready sheet rows live in [`docs/ROADMAP-SYNC-2026-06-13.md`](docs/ROADMAP-SYNC-2026-06-13.md).

**Shipped & verified:** OTP + Google OAuth (account merge), unified role routing, room
availability + 10-min hold + auto-release, Razorpay webhook with HMAC, invoice generation
(`TT-YYYY-XXXXX` + tax engine), invoice email, WhatsApp confirmation, loyalty award + tier
promotion, financial masking, both admin micro-apps, and the Things To Do / Explore pages.

**Remaining V2 work (the only open items):**

| Priority | Item | Notes |
|----------|------|-------|
| P1 | Guest-facing loyalty page | `loyalty/views.py` is an empty stub — guests can't view points/tier yet |
| P1 | Tier-upgrade email | Tier promotion happens silently; needs a notification on upgrade |
| P1 | Availability calendar API | No `GET /api/properties/{id}/calendar/` endpoint yet |
| P2 | Coupon redemption | No `Coupon` model / `redeem` / `apply_coupon` — only a ledger-reason placeholder |

**V3 (not started, expected):** OTA channel-manager sync, full loyalty campaigns, Volunteer /
Travel for a Cause, analytics dashboard.

---

## 🚪 Portal Access & Role Routing

Authentication is centralized at `/accounts/login/page/`. The system intercepts logins and dynamically routes users based on their assigned role:

| Portal | URL Path | Role Requirement | Description |
|--------|----------|------------------|-------------|
| **Guest Folio** | `/` | `guest` | Browse rooms, book, view upcoming/past stays. |
| **Staff Dashboard** | `/admin-portal/` | `employee`, `employee_admin` | Scoped operational control. Employees only see/manage rooms and bookings for **properties assigned to them**. |
| **Super Admin** | `/super-admin/` | `super_admin` | Absolute platform control. Manages employees, global pricing, tax configs, loyalty tiers, and reviews immutable Audit Logs. |

---

## 🛠️ Local Development & Setup

### 1. Environment & Dependencies
```bash
# Clone and enter the directory
git clone <repo-url>
cd TTR-V2

# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Environment Variables
Copy the example environment file and fill in your details:
```bash
cp .env.example .env
```
Ensure you have the following critically set for local dev:
- `DEBUG=True`
- `SECRET_KEY`
- `RAZORPAY_KEY_ID` & `RAZORPAY_KEY_SECRET`
- `EMAIL_HOST_USER` & `EMAIL_HOST_PASSWORD` (For SMTP/OTP emails)

### 3. Database & Migrations
The project defaults to MySQL (configured in `hotel_booking/settings/base.py`). Ensure your local MySQL server is running and the database (`ttr_v2`) is created.
```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Create a Super Admin
```bash
python manage.py createsuperuser
```

### 5. Running the Application (CRITICAL)
TTR-V2 **requires** both the web server and the background worker to run simultaneously. The worker is responsible for expiring 10-minute holds and sending emails.

**Terminal 1 (Web Server):**
```bash
python manage.py runserver
```

**Terminal 2 (Background Worker):**
```bash
python manage.py qcluster
```

---

## 📂 Codebase Structure & Rules

The project strictly follows the **Django MVT** (Model-View-Template) pattern.

- `accounts/`: Custom User model, OTP logic, pending registrations, and role-based routing.
- `rooms/`: Room inventory, `Property` definitions, `Booking` holds, and dynamic seasonal `RoomRate` pricing.
- `payments/`: Razorpay integration, webhook handling, HMAC validation, and `Payment` audit models.
- `core/`: Shared utilities, landing pages, static files, and background task definitions.
- `superadmin/`: Full platform control views, immutable `AuditLog`, and `PropertyTaxConfig`.
- `employeeadmin/`: Scoped views restricting staff to their assigned properties for CRUD operations.
- `loyalty/`: Points engine — `award_booking_points()` and tier promotion (`LoyaltyConfig`, `LoyaltyTier`, `CampaignRule`, `LoyaltyLedger`). All rules DB-driven, configured by Super Admin.

### 📜 Development Guidelines
1. **Fat Models, Thin Views**: Business logic (`expire_if_needed()`, availability checks, dynamic price calculations) belongs in `models.py`. `views.py` is strictly for request handling and orchestration.
2. **No View Logic in URLs**: `urls.py` is for routing only.
3. **No Direct `base.py` Modifictions**: Use `dev.py` for local overrides (like SQLite fallbacks if needed) and `prod.py` for production.
4. **Scoped Queries**: In `employeeadmin`, ALWAYS use `_assigned_rooms(request)` or `_assigned_properties(request)` to prevent cross-property data leaks.

---

## 🧪 Testing

The platform includes a robust suite of unit tests verifying role routing, password resets, scoped property access, hold expirations, and more.

To run the complete test suite:
```bash
python manage.py test
```
*(Currently all 40+ system-wide tests are passing).*
