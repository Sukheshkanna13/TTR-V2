# Audit 02 — Razorpay Payment Flow & Side Effects

**Scope:** `payments/views.py`, `payments/models.py`, `payments/serializers.py`, `payments/utils.py`, `payments/urls.py`; boundary trace into `rooms/models.py` (`Booking`).
**Mode:** Read-only data-flow audit.
**Date:** 2026-06-17

The HMAC signature verification itself is implemented correctly (delegates to Razorpay SDK `verify_payment_signature` for the browser path, and uses `hmac.compare_digest` constant-time compare for the webhook path). The bugs below are about what the verified-but-unvalidated data is then trusted to mean, idempotency, and atomicity.

## Summary

| ID | Severity | Title | Location |
|------|----------|-------|----------|
| PAY-01 | Critical | Paid amount never verified against booking total — pay any amount, get confirmed | `payments/views.py:201-236`, `payments/views.py:381-396` |
| PAY-02 | High | No idempotency guard / no row lock between `verify` and `webhook` → double loyalty credit + double emails | `payments/views.py:182-264`, `payments/views.py:376-410` |
| PAY-03 | High | Confirmation is non-atomic: status flip, reference, tax, side-effects are separate saves with no transaction | `payments/views.py:234-264`, `payments/views.py:382-410` |
| PAY-04 | Medium | Float arithmetic on currency: `int(float(amount_inr) * 100)` can round paise wrong | `payments/utils.py:45`, `payments/utils.py:71` |
| PAY-05 | Medium | No unique constraint on `Payment.razorpay_order_id`; `.filter(order_id).update()` mutates *all* matching rows | `payments/models.py:34`, `payments/views.py:203-209`, `243-249`, `391-396` |
| PAY-06 | Medium | Webhook trusts `payment_id`/`order_id` from JSON body but never confirms the captured amount or that the payment belongs to that order | `payments/views.py:342-396` |
| PAY-07 | Low | Hold-expiry is re-checked in `create-order` but NOT in `verify`; an expired booking that slips through is still confirmable; race on expiry vs. payment | `payments/views.py:191-236` |
| PAY-08 | Low | `compute_tax()` swallows all exceptions and silently writes `0.00` tax on a confirmed, invoiced booking | `rooms/models.py:477-491` |

---

## PAY-01 — Paid amount never verified against the booking total (Critical)

**Location:** `payments/views.py:201-236` (browser verify) and `payments/views.py:381-396` (webhook).

**Data flow:**
1. `create-order` builds a Razorpay order for `booking.total_price` (`views.py:93-96`) and stores `razorpay_order_id` on the booking.
2. On `verify`, the view receives `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature` from the browser (`views.py:165-167`).
3. `verify_razorpay_signature(order_id, payment_id, signature)` (`utils.py:82-103`) confirms only that `order_id|payment_id` was signed with the key secret.
4. The view then sets `booking.status = "confirmed"` (`views.py:234`) — **without ever fetching the payment from Razorpay and checking the captured `amount` against `booking.total_price`.**

**Why it's a bug:** A valid signature proves *a* payment exists for *that order*, not that the correct amount was paid. Razorpay's own docs require fetching the payment (`client.payment.fetch(payment_id)`) and asserting `amount == order.amount` and `status == "captured"`. Here, the order was created server-side with the right amount, which mitigates the classic "client sends amount" hole — but there is no check that the captured payment's amount equals the order amount, nor that the payment is actually captured (a `created`/`authorized` payment with a valid signature would still confirm the booking). Combined with PAY-06, the webhook path is worse: it reads `order_id`/`payment_id` straight out of the POSTed JSON and confirms on `event == "payment.captured"` with no amount assertion at all.

**Impact:** Under-payment / partial-capture / authorized-not-captured payments can confirm a booking, send an invoice, and credit loyalty points. Revenue loss and reconciliation breakage. Marked Critical because it is a money-trust-boundary gap on the confirmation path.

---

## PAY-02 — No idempotency guard; `verify` and `webhook` can both process the same payment (High)

**Location:** `payments/views.py:182-264` (verify), `payments/views.py:376-410` (webhook).

**Data flow:**
- Both endpoints guard with `if booking.status == "confirmed": return` (`views.py:182-189`, `376-378`) and then `if booking.status == "pending"` proceed to flip + fire side effects.
- The read of `booking.status` and the write `booking.status = "confirmed"` are **not inside a transaction and not behind `select_for_update()`**.

**Why it's a bug:** The browser `verify` call and the Razorpay `webhook` (whose whole purpose per the docstring at `views.py:293-298` is to catch the "browser crashed after payment" case) routinely fire for the same payment. With no lock, two concurrent requests can each read `status == "pending"`, each pass the guard, and each run the full side-effect block: `award_loyalty_points` twice (double points credited to the ledger), `send_invoice_email` twice, `send_booking_confirmation_email` twice, and the WhatsApp `async_task` queued twice. There is no unique constraint on the `Payment` row or any "already credited" flag to make the side effects idempotent.

**Impact:** Duplicate loyalty point grants (real financial value in the loyalty program), duplicate invoice/confirmation emails, duplicate WhatsApp messages. Likelihood is non-trivial because dual confirmation paths are by design.

---

## PAY-03 — Confirmation side-effects are non-atomic (High)

**Location:** `payments/views.py:234-264` and `payments/views.py:382-410`.

**Data flow:** The success path executes as a sequence of independent writes and calls:
```
booking.status = "confirmed"; booking.save(update_fields=["status","hold_expires_at"])   # 234-236
booking.generate_booking_reference()   # 239  → its own .save() (and its own atomic block, models.py:466)
booking.compute_tax()                  # 240  → its own .save()
Payment.objects.filter(...).update(status="captured")  # 243-249
send_booking_confirmation_email(booking)  # 260
send_invoice_email(booking)               # 263
award_loyalty_points(booking)             # 264
```
None of this is wrapped in a single `transaction.atomic()`.

**Why it's a bug:** A failure or crash between any two steps leaves inconsistent state: e.g. status flipped to `confirmed` but `booking_reference` not yet generated, then the invoice email (`send_invoice_email`, utils.py:178-181) renders `Ref: None`; or status `confirmed` but the `Payment` row still `created`. Because each call saves independently, there is no rollback boundary. (Side effects are correctly wrapped in try/except so email/WhatsApp/loyalty failures don't 500 — that part is good — but the *database* writes are not transactional as a unit.)

**Impact:** Confirmed bookings with missing references, wrong/zero tax, or `Payment` rows stuck in `created` after a mid-sequence error. Hard to reconcile and to refund correctly.

---

## PAY-04 — Float arithmetic on currency (Medium)

**Location:** `payments/utils.py:45` and `payments/utils.py:71`.

```python
amount_paise = int(float(amount_inr) * 100)   # line 45
data["amount"] = int(float(amount_inr) * 100) # line 71 (refund)
```

**Data flow:** `booking.total_price` is a `DecimalField` (`rooms/models.py:343-346`). It is cast to `float`, multiplied by 100, then truncated with `int()`.

**Why it's a bug:** `int(float(x) * 100)` truncates (not rounds) and is subject to binary float representation error. For example `int(float(Decimal("4999.99")) * 100)` can yield `499998` instead of `499999` because `4999.99 * 100 == 499998.99999...`. The correct pattern is `int((Decimal(amount_inr) * 100).quantize(Decimal("1")))` or `int(Decimal(amount_inr) * 100)`. The same truncation bug is in the refund path, so a refund can be 1 paise short.

**Impact:** Order amount can be 1 paise less than `total_price` for certain decimals — payment succeeds but ties into PAY-01 (no amount reconciliation hides it), and refunds can be off-by-one-paise.

---

## PAY-05 — No unique constraint on `Payment.razorpay_order_id`; bulk `.update()` hits all rows (Medium)

**Location:** `payments/models.py:34` (field has no `unique=True`, no `Meta` constraint); `payments/views.py:203-209`, `243-249`, `359-361`, `391-396`.

**Data flow:** Every status mutation is `Payment.objects.filter(razorpay_order_id=order_id).update(...)`. The field is a plain `CharField`. If more than one `Payment` row ever shares an `order_id` (e.g. a retry that re-runs `create-order` — note `create-order` will refuse on non-pending status, but a failed→released booking, or any future re-issue, can create a second row), the `.update()` rewrites *every* matching row, and the "already confirmed?" guard keys off the *booking*, not the payment, so the payment ledger can disagree with reality.

**Why it's a bug:** There is no DB guarantee of one Payment per order, and the code assumes exactly one. A `.filter().update()` is a silent multi-row write. Idempotency (PAY-02) would normally be enforceable with a `unique=True` here plus `get_or_create`, but neither exists.

**Impact:** Payment audit table can hold ambiguous/duplicate rows; bulk update mutates unintended rows; weakens any future idempotency fix.

---

## PAY-06 — Webhook trusts payload identifiers without confirming amount or payment authenticity (Medium)

**Location:** `payments/views.py:342-396`.

**Data flow:** The webhook signature (`verify_webhook_signature`, utils.py:106-123) is verified correctly over the raw body — so the *body* is authentic. But after that, the handler reads `order_id` and `payment_id` from the JSON (`views.py:343-345`) and, on `payment.captured`, flips the booking to `confirmed` and fires all side effects **without checking the captured `amount` in `payment_entity` against `booking.total_price`**, and without fetching the payment from Razorpay.

**Why it's a bug:** Same trust gap as PAY-01 on the server-to-server path. The signature guarantees the event came from Razorpay, but the handler never asserts `payment_entity["amount"] == int(booking.total_price * 100)` or `payment_entity["status"] == "captured"`. A `payment.captured` event for a partially-captured or differently-valued payment confirms the booking.

**Impact:** Booking confirmed on a webhook for an amount that may not match the order total; no amount reconciliation anywhere in the flow.

---

## PAY-07 — Hold expiry not re-checked at verify; expiry vs. payment race (Low)

**Location:** `payments/views.py:191-236`.

**Data flow:** `create-order` calls `booking.expire_if_needed()` (`views.py:82`). `verify` does **not** — it only checks `status == "pending"` (`views.py:192`). The `qcluster` background task and `release_hold` can flip a booking to `expired`/`failed` at any moment.

**Why it's a bug:** If the hold expires (background task sets `expired`) *after* the user paid but *before* `verify` runs, `verify` sees `status != "pending"` and returns `400 "Cannot verify payment for booking with status: Expired"` — the guest has paid but the booking is dead, with no auto-refund triggered. Conversely there is no `select_for_update`, so the expiry task and `verify` race on the same row. The webhook path (designed to recover crashed-browser cases) also only acts on `status == "pending"` (`views.py:381`), so an expired-but-paid booking is silently dropped there too (`logged`, returns 200).

**Impact:** Paid-but-expired bookings that neither confirm nor auto-refund; manual reconciliation required. Low severity because the 10-minute window makes it rare, but it is a real money-vs-state race.

---

## PAY-08 — `compute_tax()` silently writes 0.00 on broad except (Low)

**Location:** `rooms/models.py:477-491` (called from `views.py:240` and `views.py:387`).

**Data flow:** `compute_tax` wraps the entire GST computation in `except Exception: self.tax_amount = Decimal('0.00')`.

**Why it's a bug:** Any error (missing `tax_config`, null property, arithmetic issue) is swallowed and the booking is saved with `tax_amount = 0.00`, then the invoice email is sent (`send_invoice_email`, utils.py:168-210) reflecting zero GST. There is no log line in the except branch, so a misconfigured property silently issues tax-free invoices.

**Impact:** Incorrect (zero) GST on invoices for misconfigured properties, with no signal that anything went wrong. Compliance/accounting risk.

---

## Notes on things that are correct (not bugs)
- HMAC verification uses the SDK / `hmac.compare_digest` — constant-time, right fields. No `==` comparison on secrets.
- No path confirms a booking without *some* signature check (browser verify and webhook both gate on signature).
- Card data is not stored — only order/payment/signature references (`payments/models.py`).
- Side-effect calls (email, WhatsApp, loyalty) are wrapped so their failure does not 500 the confirmation response — the user-facing response is decoupled from side-effect failures. (The remaining gap is DB atomicity, PAY-03.)
