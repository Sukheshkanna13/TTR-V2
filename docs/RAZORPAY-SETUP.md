# Razorpay Gateway Setup & Integration Guide

This document contains the exact steps to configure, verify, and activate Razorpay payment processing for Temple and Towns Resorts (TTR-V2) when production or test credentials arrive.

---

## 1. Credentials Checklist

You will need three values from the [Razorpay Dashboard](https://dashboard.razorpay.com):

| Environment Variable | Description | Example Format |
|---|---|---|
| `RAZORPAY_KEY_ID` | Public identifier (used by backend and checkout JS) | `rzp_test_...` (dev) / `rzp_live_...` (prod) |
| `RAZORPAY_KEY_SECRET` | Private secret key (used for HMAC-SHA256 signature verification) | 24-character alphanumeric string |
| `RAZORPAY_WEBHOOK_SECRET` | Secret token used to verify Razorpay webhook callbacks | Custom secret configured in Webhooks dashboard |

> [!CAUTION]
> Never commit `RAZORPAY_KEY_SECRET` or `RAZORPAY_WEBHOOK_SECRET` to version control. They should only exist in `.env` (locally) or in the hosting environment variables (e.g., Render Dashboard).

---

## 2. Step-by-Step Setup

### Step 1: Generate API Keys

1. Log in to the [Razorpay Dashboard](https://dashboard.razorpay.com).
2. Use the top toggle to select **Test Mode** (for testing/certification) or **Live Mode** (for real customer transactions).
3. In the left navigation, go to **Account & Settings** $\rightarrow$ **API Keys** (under *Website and app settings*).
4. Click **Generate Key** (or *Regenerate Key* if replacing older keys).
5. Copy both the **Key ID** and the **Key Secret**.
   * *Note: The Key Secret will only be shown once. Save it immediately in a secure password manager.*

---

### Step 2: Configure Server-to-Server Webhook

Razorpay webhooks ensure that bookings are confirmed even if a guest's browser closes or their internet drops before the front-end redirect finishes.

1. In Razorpay Dashboard, go to **Account & Settings** $\rightarrow$ **Webhooks**.
2. Click **Add New Webhook**.
3. Fill in the webhook form:
   * **Webhook URL**:
     * **Local dev / testing:** `https://<your-ngrok-or-tunnel-url>/payments/webhook/`
     * **Production (Render):** `https://<your-app>.onrender.com/payments/webhook/` (or `https://templetownsresorts.com/payments/webhook/`)
   * **Secret**: Enter a secure random string (e.g. 24–32 random characters). Copy this string as it is your `RAZORPAY_WEBHOOK_SECRET`.
   * **Active Events**: Check the following required events:
     * `payment.captured` *(confirms booking and sends confirmation email & invoice)*
     * `payment.failed` *(releases room hold so room returns to bookable inventory)*
     * `refund.processed` *(updates payment status to refunded and marks refund ID)*
4. Click **Create Webhook**.

---

### Step 3: Configure Environment Variables

#### A. Local Development (`.env`)
Update your local `.env` file with the keys:

```ini
# Razorpay Payment Gateway
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
```

#### B. Production (Render Dashboard)
When deploying to Render:
1. Open your [Render Dashboard](https://dashboard.render.com).
2. Go to the web service (`ttr-v2`) $\rightarrow$ **Environment**.
3. Add:
   * `RAZORPAY_KEY_ID`
   * `RAZORPAY_KEY_SECRET`
   * `RAZORPAY_WEBHOOK_SECRET`
4. Go to the worker service (`ttr-v2-worker`) $\rightarrow$ **Environment**.
5. Add the same three keys so that background tasks and invoice generation have access to payment details.
6. Click **Save Changes**. Render will automatically re-deploy with the new variables.

---

## 3. Architecture & Security Invariants

* **Server-side Signature Verification:** Never trust client-side parameters. [`payments/views.py`](file:///d:/Sukhesh_V2/payments/views.py) verifies `razorpay_signature` using HMAC-SHA256 (`order_id + "|" + payment_id` with `RAZORPAY_KEY_SECRET`).
* **Auto-Capture:** Orders are created with `"payment_capture": 1` in [`payments/utils.py`](file:///d:/Sukhesh_V2/payments/utils.py). Captured payments settle into the merchant account automatically.
* **Webhook Idempotency:** Every webhook request is logged in [`ProcessedWebhookEvent`](file:///d:/Sukhesh_V2/payments/models.py). If Razorpay retries a webhook, the system detects the event ID and exits early to prevent duplicate booking confirmations or duplicate loyalty credits.
* **10-Minute Hold Abandonment:** If the user dismisses the Razorpay modal (`ondismiss`) or payment fails (`payment.failed`), the room hold is instantly released back to inventory via `POST /bookings/<id>/release/`.

---

## 4. Testing & Verification

### Test Cards & UPI (Razorpay Test Mode)

When using a `rzp_test_...` key, test with the following mock credentials in the checkout popup:

| Method | Test Details | OTP / PIN |
|---|---|---|
| **Test Cards** | Card Number: `4111 1111 1111 1111`<br>Expiry: Any future date (e.g. `12/30`)<br>CVV: `123` | Click **Success** on bank emulator screen |
| **Test UPI** | Enter any VPA, e.g. `success@razorpay` | Click **Success** on simulated UPI approval screen |

### Verification Steps

1. Select an available room and proceed to checkout: `/payments/checkout/page/?booking_id=<id>`.
2. Ensure guest name, email, and phone are prefilled into the Razorpay modal.
3. Complete payment with test card.
4. Verify:
   * Browser redirects to `/bookings/confirmation/?ref=<REF>`.
   * Booking status in Django Admin is updated to **Confirmed** (`status="confirmed"`).
   * Payment record in Django Admin has `status="captured"`, with `razorpay_payment_id` populated.
   * Confirmation email with invoice attachment arrives at the guest's email.
   * `ProcessedWebhookEvent` records the webhook event in Django Admin.

---

## 5. Troubleshooting & FAQs

| Symptom | Cause | Solution |
|---|---|---|
| `Razorpay order creation failed: Authentication failed` | Invalid Key ID or Key Secret in `.env` | Double check `.env` for extra spaces or typo in `RAZORPAY_KEY_ID` or `RAZORPAY_KEY_SECRET`. Restart server. |
| `Signature verification failed` | Mismatched secret or tampered payload | Ensure `RAZORPAY_KEY_SECRET` in `.env` matches the key used to generate the order. |
| `Webhook 400 Bad Request / Signature mismatch` | `RAZORPAY_WEBHOOK_SECRET` does not match the secret in Razorpay dashboard | Update `RAZORPAY_WEBHOOK_SECRET` to match the exact secret string defined in Razorpay dashboard. |
| Test modal shows "Invalid Key ID" | Key ID is blank or inactive | Confirm `settings.RAZORPAY_KEY_ID` is not empty. Inspect browser network response from `/payments/create-order/`. |
