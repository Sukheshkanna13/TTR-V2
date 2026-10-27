# Temple & Towns Resorts (TTR-V2) — Manual Smoke Test Checklist

This checklist documents the **13 core end-to-end flows** required for pre-release certification, regression testing, and deployment verification.

---

## Pre-Flight Checklist

Before running tests, ensure the environment is running:
- [ ] Dev web server running: `python manage.py runserver` (port 8000)
- [ ] Background worker running: `python manage.py qcluster`
- [ ] Database migrated: `python manage.py migrate`
- [ ] Test credentials configured in `.env` (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`)

---

## 1. Guest Registration with Email + OTP Verification

* **Goal:** Verify that a new guest can register, receive an OTP verification email, and activate their account.
* **Test Steps:**
  1. Open a browser and navigate to `/accounts/register/page/`.
  2. Fill in **Full Name**, **Email**, **Phone**, and **Password**.
  3. Click **Create account**.
  4. Verify the page transitions to the OTP entry form.
  5. Check inbox for the 6-digit OTP code.
  6. Enter the OTP and submit.
* **Expected Result:**
  - Account is activated (`is_active=True`).
  - Guest is logged in and redirected to homepage `/` or folio.
  - Submitting an invalid OTP displays an error and leaves the account inactive.

---

## 2. Google OAuth Sign-In & Account Merging

* **Goal:** Verify Google Single Sign-On and automatic account merging for existing email addresses.
* **Test Steps:**
  1. Navigate to `/accounts/login/page/`.
  2. Click **Continue with Google**.
  3. Authenticate with a Google account whose email matches an existing registered user.
* **Expected Result:**
  - `accounts/adapter.py` merges the Google identity with the existing user account without throwing a duplicate email error.
  - User session is established and redirected to `/`.

---

## 3. Forgot Password 3-Step OTP Recovery

* **Goal:** Verify that a user can reset a forgotten password using OTP verification.
* **Test Steps:**
  1. Navigate to `/accounts/forgot-password/`.
  2. **Step 1:** Enter the registered email address and click **Send OTP**.
  3. **Step 2:** Verify page redirects to `/accounts/forgot-password/verify/`. Check email, enter 6-digit OTP, and click **Verify OTP**.
  4. **Step 3:** Verify page redirects to `/accounts/forgot-password/set/`. Enter and confirm a new password ($\ge$ 8 chars).
  5. Attempt login with the old password (must fail).
  6. Attempt login with the new password (must succeed).
  7. **Security Check:** Attempt direct navigation to `/accounts/forgot-password/set/` in a fresh incognito tab without verifying OTP $\rightarrow$ must redirect back to Step 1.
* **Expected Result:**
  - Password resets securely without link tokens.
  - Session flags (`pw_reset_email`, `pw_reset_verified`) are cleared upon completion.

---

## 4. Room Search & Real-Time Availability with UX Signals

* **Goal:** Verify property search filtering and live UX signals.
* **Test Steps:**
  1. Navigate to `/rooms/search/page/` (or use homepage search bar).
  2. Select City or Property, check-in date (future), check-out date, and guests count.
  3. Click **Search Rooms**.
  4. Observe the search result cards.
  5. Change filters (e.g. Price Sort: High to Low, Room Type: Villa).
* **Expected Result:**
  - Only active rooms with `operational_status="available"` matching criteria are listed.
  - Live UX signals ("Only X rooms left", "Popular Choice") display dynamically.
  - No rooms with overlapping confirmed bookings or active holds appear.

---

## 5. 10-Minute Room Hold & Double-Booking Locking

* **Goal:** Verify that initiating checkout locks the room for 10 minutes and blocks double-booking.
* **Test Steps:**
  1. Click **Book Now** on an available room.
  2. Redirects to `/payments/checkout/page/?booking_id=<uuid>`.
  3. Observe the countdown timer ("10-minute hold active — Expires in 09:59").
  4. In a separate incognito window, perform the exact same search for the same room and dates.
* **Expected Result:**
  - The second browser does not show the held room (or indicates it is currently held).
  - Booking record in DB has `status="pending"` and `hold_expires_at` set 10 minutes in the future.

---

## 6. Room Hold Early Release (Abandonment & Unload)

* **Goal:** Verify that abandoning checkout frees the room immediately without waiting 10 minutes.
* **Test Steps:**
  1. On the checkout page, test each abandonment trigger:
     - Click **Pay now with Razorpay**, then dismiss the modal (click X or backdrop).
     - Click the **Back to Search** button and confirm the modal dialog.
     - Close or navigate away from the browser tab (`pagehide` beacon).
  2. Immediately switch to the second browser and refresh the search.
* **Expected Result:**
  - `POST /bookings/<id>/release/` triggers immediately.
  - Booking status moves to `"expired"`.
  - The room instantly reappears in search results for other guests.

---

## 7. Coupon / Voucher Application on Checkout

* **Goal:** Verify promo code and loyalty voucher discount calculations.
* **Test Steps:**
  1. On the checkout page, locate the **Apply Coupon / Voucher** section.
  2. Click an active voucher pill (or enter promo code `TTR-WELCOME`).
  3. Click **Apply**.
  4. Observe the price breakdown table.
  5. Click **Remove**.
* **Expected Result:**
  - Discount line item appears with savings amount.
  - Taxes and Total Payable recalculate accurately.
  - Removing the coupon restores original prices.

---

## 8. Razorpay Checkout with Prefilled Guest Data

* **Goal:** Verify seamless checkout prefill and modal integration.
* **Test Steps:**
  1. On the checkout page, click **Pay now with Razorpay**.
  2. Inspect the opened Razorpay payment popup.
* **Expected Result:**
  - Guest's **Full Name**, **Email**, and **Phone** are automatically prefilled in Razorpay.
  - Total amount in Razorpay matches the `Total Payable` amount (in paise).
  - Theme styling matches brand specifications.

---

## 9. Payment Verification & Booking Confirmation

* **Goal:** Verify payment signature verification, reference generation, and invoice delivery.
* **Test Steps:**
  1. In the Razorpay modal, complete payment using test card (`4111 1111 1111 1111`, CVV `123`).
  2. Click **Success** on the simulated bank verification screen.
* **Expected Result:**
  - Front-end displays "Verifying payment...".
  - Server verifies HMAC-SHA256 signature against `RAZORPAY_KEY_SECRET`.
  - Page redirects to `/bookings/confirmation/page/?ref=<REFERENCE>`.
  - Confirmation card displays booking reference, dates, room details, and amount paid.
  - Booking confirmation email with PDF invoice attachment is sent to guest's email.
  - In Django Admin: `Booking.status == "confirmed"`, `Payment.status == "captured"`.

---

## 10. Server-to-Server Webhook Fallback & Idempotency

* **Goal:** Verify webhook reliability and replay attack protection.
* **Test Steps:**
  1. Send a simulated `payment.captured` event to `POST /payments/webhook/` with valid header `X-Razorpay-Signature`.
  2. Send the exact same webhook payload a second time.
  3. Send a `payment.failed` event for an unpaid booking.
* **Expected Result:**
  - First capture webhook confirms booking and creates a row in `ProcessedWebhookEvent`.
  - Duplicate webhook returns `200 OK` with `{"status": "already_processed"}` (idempotent).
  - `payment.failed` webhook marks payment failed and releases the room hold.
  - Request with invalid signature header returns `400 Bad Request`.

---

## 11. Booking Cancellation & Automated Razorpay Refund

* **Goal:** Verify guest booking cancellation and automated refund handling.
* **Test Steps:**
  1. As a logged-in guest, go to `/accounts/folio/` (My Stays).
  2. Locate the confirmed booking and click **Cancel Booking**.
  3. Confirm the cancellation prompt.
* **Expected Result:**
  - `POST /bookings/<id>/cancel/` initiates refund via `refund_razorpay_payment()`.
  - Booking status moves to `"cancelled"`.
  - In Django Admin: `Payment.status == "refunded"`, `refund_id` and `refund_status` are populated.
  - Room returns to available inventory for those dates.

---

## 12. Employee Admin Portal & Daily Operations

* **Goal:** Verify staff room management and status transitions.
* **Test Steps:**
  1. Log in with an Employee account at `/admin-portal/login/`.
  2. Access the Room Management dashboard.
  3. Select a room and toggle operational status from `"cleaning"` to `"available"`.
  4. Create an on-premise walk-in booking.
  5. Verify Level C staff restrictions (financial totals hidden for Level C employees).
* **Expected Result:**
  - Operational status changes take effect immediately in guest search.
  - Walk-in booking locks the room and generates a booking reference.
  - Role-based permissions are enforced.

---

## 13. Super Admin Portal & Automated Background Sweeps

* **Goal:** Verify platform-wide management and scheduled task execution.
* **Test Steps:**
  1. Log in with Super Admin credentials at `/super-admin/login/`.
  2. Review analytics dashboard (Revenue, Occupancy, Bookings overview).
  3. Verify all 6 django-q scheduled tasks exist and are running via `qcluster`:
     - `rooms.tasks.release_expired_holds` (1 min)
     - `core.ota.tasks.process_ari_outbox` (1 min)
     - `rooms.tasks.auto_complete_bookings` (Daily)
     - `rooms.tasks.award_loyalty_for_completed_stays` (Hourly)
     - `core.ota.tasks.nightly_full_sync` (Daily)
     - `core.ota.tasks.poll_booking_feed` (15 min)
* **Expected Result:**
  - Super admin has platform-wide visibility across all properties.
  - `qcluster` processes queue items without errors.
  - Stale bookings auto-complete and loyalty points credit 24h after checkout.

---

## Smoke Test Sign-Off Matrix

| Flow # | Flow Name | Tester | Date | Result (Pass/Fail) | Notes |
|---|---|---|---|---|---|
| 1 | Guest Registration + Email OTP | | | | |
| 2 | Google OAuth + Account Merge | | | | |
| 3 | Forgot Password 3-Step OTP | | | | |
| 4 | Room Search & Scarcity Signals | | | | |
| 5 | 10-Minute Hold & Lock | | | | |
| 6 | Hold Early Abandonment | | | | |
| 7 | Coupon / Voucher Application | | | | |
| 8 | Razorpay Prefill Integration | | | | |
| 9 | Payment Verify & Invoice Email | | | | |
| 10 | Webhook Fallback & Idempotency | | | | |
| 11 | Cancellation & Razorpay Refund | | | | |
| 12 | Employee Portal & Operations | | | | |
| 13 | Super Admin & Background Sweeps| | | | |
