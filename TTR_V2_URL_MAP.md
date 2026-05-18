# TTR-V2 — URL / Function / Logic Map

---

## URLs

### Public Pages & Core

| URL | Function | File | Line | Methods | Auth |
|-----|----------|------|------|---------|------|
| `/` | `home_page` | `core/views.py` | 9 | GET | Public |
| `/experiences/` | `experiences_page` | `core/views.py` | 21 | GET | Public |
| `/things-to-do/` | `things_to_do_page` | `core/views.py` | 26 | GET | Public |
| `/cause/` | `cause_page` | `core/views.py` | 31 | GET | Public |
| `/explore/` | `explore_page` | `core/views.py` | 36 | GET | Public |
| `/admin/` | Django admin | built-in | — | GET/POST | `is_superuser` |
| `/auth/` | allauth | built-in | — | — | — |

### Accounts — Pages

| URL | Function | File | Line | Methods | Auth |
|-----|----------|------|------|---------|------|
| `/accounts/login/page/` | `login_page` | `accounts/views.py` | 422 | GET | Public |
| `/accounts/register/page/` | `register_page` | `accounts/views.py` | 426 | GET | Public |
| `/accounts/folio/` | `folio_page` | `accounts/views.py` | 512 | GET | `@login_required` |
| `/accounts/profile/edit/` | `edit_profile_page` | `accounts/views.py` | 532 | GET | `@login_required` |
| `/accounts/forgot-password/` | `forgot_password` | `accounts/views.py` | 657 | GET/POST | Public |
| `/accounts/forgot-password/verify/` | `forgot_password_verify` | `accounts/views.py` | 675 | GET/POST | Public |
| `/accounts/forgot-password/set/` | `forgot_password_set` | `accounts/views.py` | 693 | GET/POST | Public |
| `/admin-portal/login/` | `employee_login_page` | `accounts/views.py` | 430 | GET/POST | Public |
| `/super-admin/login/` | `super_admin_login_page` | `accounts/views.py` | 467 | GET/POST | Public |

### Accounts — API

| URL | Class | File | Line | Methods | Auth | Response |
|-----|-------|------|------|---------|------|----------|
| `/accounts/register/` | `RegisterView` | `accounts/views.py` | 51 | POST | Public | 201 `{message, email, next_step}` |
| `/accounts/verify-otp/` | `VerifyOTPView` | `accounts/views.py` | 101 | POST | Public | 200 `{message, email, next_step}` |
| `/accounts/set-password/` | `SetPasswordView` | `accounts/views.py` | 190 | POST | Public | 201 `{message, user}` |
| `/accounts/resend-otp/` | `ResendOTPView` | `accounts/views.py` | 304 | POST | Public | 200 `{message}` |
| `/accounts/login/` | `LoginView` | `accounts/views.py` | 340 | POST | Public | 200 `{message, user}` |
| `/accounts/logout/` | `LogoutView` | `accounts/views.py` | 396 | GET/POST | `IsAuthenticated` | GET → redirect, POST → 200 |
| `/accounts/me/` | `CurrentUserView` | `accounts/views.py` | 411 | GET | `IsAuthenticated` | 200 `{user}` |
| `/accounts/profile/update/` | `update_profile` | `accounts/views.py` | 540 | POST | `@login_required` | JSON |
| `/admin-api/employees/create/` | `CreateEmployeeView` | `accounts/views.py` | 607 | POST | `IsSuperAdmin` | 200 `{message, temp_password}` |

### Rooms

| URL | Class | File | Line | Methods | Auth | Response |
|-----|-------|------|------|---------|------|----------|
| `/rooms/search/page/` | `search_page` | `rooms/views.py` | 806 | GET | Public | `rooms/search.html` |
| `/rooms/room/page/` | `room_detail_page` | `rooms/views.py` | 823 | GET | Public | `rooms/room_details.html` |
| `/rooms/search/` | `SearchRoomsView` | `rooms/views.py` | 81 | GET/POST | Public | 200 `{rooms[], search{}}` |
| `/rooms/<uuid>/` | `RoomDetailView` | `rooms/views.py` | 214 | GET | Public | 200 `{room}` |

### Bookings

| URL | Class | File | Line | Methods | Auth | Response |
|-----|-------|------|------|---------|------|----------|
| `/bookings/my-bookings/page/` | `my_bookings_page` | `rooms/views.py` | 831 | GET | Public | `bookings/my_bookings.html` |
| `/bookings/confirmation/page/` | `confirmation_page` | `rooms/views.py` | 836 | GET | Public | `bookings/confirmation.html` |
| `/bookings/hold/` | `HoldRoomView` | `rooms/views.py` | 242 | POST | `IsAuthenticated` | 201 `{booking, payment{order_id, amount, key_id}}` |
| `/bookings/<uuid>/` | `BookingDetailView` | `rooms/views.py` | 541 | GET | `IsAuthenticated` | 200 `{booking}` |
| `/bookings/<uuid>/cancel/` | `CancelBookingView` | `rooms/views.py` | 480 | POST | `IsAuthenticated` | 200 `{message, booking}` |
| `/bookings/<uuid>/pay/` | `ProcessPaymentView` | `rooms/views.py` | 398 | POST | `IsAuthenticated` | Debug only — 403 in prod |
| `/bookings/ref/<str>/confirmation/` | `ConfirmationView` | `rooms/views.py` | 571 | GET | `IsAuthenticated` | 200 `{confirmation}` |
| `/bookings/my/` | `MyBookingsView` | `rooms/views.py` | 632 | GET | `IsAuthenticated` | 200 `{upcoming[], past[]}` |

### Payments

| URL | Class | File | Line | Methods | Auth | Response |
|-----|-------|------|------|---------|------|----------|
| `/payments/checkout/page/` | `checkout_page` | `payments/views.py` | 416 | GET | Public | `payments/checkout.html` |
| `/payments/create-order/` | `CreateOrderView` | `payments/views.py` | 38 | POST | `IsAuthenticated` | 201 `{order{}, booking{}}` |
| `/payments/verify/` | `VerifyPaymentView` | `payments/views.py` | 144 | POST | `IsAuthenticated` | 200 `{booking}` |
| `/payments/webhook/` | `WebhookView` | `payments/views.py` | 285 | POST | Public | 200 `{status}` |

### Employee Admin Portal (`/admin-portal/`)

| URL | Function | File | Line | Methods | Financial Level |
|-----|----------|------|------|---------|-----------------|
| `/admin-portal/dashboard/` | `dashboard` | `employeeadmin/views.py` | 30 | GET | Any |
| `/admin-portal/bookings/` | `bookings_list` | `employeeadmin/views.py` | 60 | GET | Any |
| `/admin-portal/rooms/` | `rooms_list` | `employeeadmin/views.py` | 69 | GET | Any |
| `/admin-portal/rooms/<uuid>/status/` | `room_status_update` | `employeeadmin/views.py` | 76 | POST | Any |
| `/admin-portal/availability/` | `availability` | `employeeadmin/views.py` | 88 | GET | Any |
| `/admin-portal/availability/block/create/` | `ota_block_create` | `employeeadmin/views.py` | 114 | POST | Any |
| `/admin-portal/availability/block/<uuid>/delete/` | `ota_block_delete` | `employeeadmin/views.py` | 132 | POST | Any |
| `/admin-portal/availability/rate/create/` | `seasonal_rate_create` | `employeeadmin/views.py` | 142 | POST | **A/B only** |

> All `/admin-portal/` views require `@require_employee` — `userprofile.role in ('employee', 'super_admin')`.

### Super Admin Portal (`/super-admin/`)

| URL | Function | File | Line | Methods |
|-----|----------|------|------|---------|
| `/super-admin/dashboard/` | `dashboard` | `superadmin/views.py` | 33 | GET |
| `/super-admin/employees/` | `employees_list` | `superadmin/views.py` | 64 | GET |
| `/super-admin/employees/create/` | `employee_create` | `superadmin/views.py` | 77 | POST |
| `/super-admin/employees/<int>/update/` | `employee_update` | `superadmin/views.py` | 121 | POST |
| `/super-admin/analytics/` | `analytics` | `superadmin/views.py` | 160 | GET |
| `/super-admin/tax-config/` | `tax_config` | `superadmin/views.py` | 185 | GET/POST |
| `/super-admin/loyalty-config/` | `loyalty_config` | `superadmin/views.py` | 204 | GET/POST |
| `/super-admin/audit-log/` | `audit_log` | `superadmin/views.py` | 265 | GET |
| `/super-admin/bookings/` | `bookings_list` | `superadmin/views.py` | 280 | GET |

> All `/super-admin/` views require `@require_super_admin` — `userprofile.role == 'super_admin'`.

### Calendar & Block API

| URL | Class | File | Line | Methods | Auth |
|-----|-------|------|------|---------|------|
| `/api/properties/<uuid>/calendar/` | `CalendarView` | `rooms/views.py` | 700 | GET | Public |
| `/api/block/` | `BlockRoomView` | `rooms/views.py` | 771 | POST | `IsEmployee` |
| `/api/unblock/<uuid>/` | `UnblockRoomView` | `rooms/views.py` | 786 | POST | `IsEmployee` |

---

## Utility Functions

### accounts/utils.py

| Function | Line | Returns | Notes |
|----------|------|---------|-------|
| `generate_otp()` | 23 | `str` | Cryptographically secure 6-digit code |
| `create_and_store_otp(email)` | 37 | `str` | Upserts OTP to DB, 10-min expiry |
| `verify_otp(email, code)` | 61 | `dict {success, error, code}` | Blocks after 3 wrong attempts |
| `check_login_lock(email)` | 119 | **`bool`** ⚠ | Returns True if locked — see bug |
| `record_failed_login(email)` | 133 | `int` | Locks after 5 attempts for 15 min |
| `reset_login_attempts(email)` | 158 | `None` | Clears on successful login |
| `send_otp_email(email, otp)` | 169 | `bool` | Gmail SMTP, synchronous |

### payments/utils.py

| Function | Line | Returns | Notes |
|----------|------|---------|-------|
| `get_razorpay_client()` | 21 | `razorpay.Client` | Fresh client from settings |
| `create_razorpay_order(amount_inr, booking_id)` | 31 | `dict` | Converts INR → paise |
| `refund_razorpay_payment(payment_id, amount_inr)` | 59 | `dict \| None` | Full or partial refund |
| `verify_razorpay_signature(order_id, payment_id, sig)` | 82 | `bool` | HMAC-SHA256 — critical security check |
| `verify_webhook_signature(body, sig, secret)` | 106 | `bool` | Webhook HMAC-SHA256 check |
| `send_booking_confirmation_email(booking)` | 130 | `None` | Fail-silent |
| `send_invoice_email(booking)` | 168 | `None` | HTML invoice, fail-silent |
| `award_loyalty_points(booking)` | 217 | `None` | Delegates to `loyalty.services` |

### loyalty/services.py

| Function | Line | Notes |
|----------|------|-------|
| `award_booking_points(booking_pk)` | 12 | 5-step: base pts → monthly multiplier → campaign multiplier → ledger → tier update |
| `_update_tier(profile)` | 104 | Promotes to highest tier where `min_pts ≤ loyalty_points` |
| `models_q_property_or_global(prop)` | 118 | Q filter: specific property OR platform-wide campaigns |

---

## Auth Guards

| Guard | File | Applied To | Checks |
|-------|------|------------|--------|
| `@login_required` | Django built-in | `folio_page`, `edit_profile_page`, `update_profile` | Any active session |
| `@require_employee` | `employeeadmin/views.py` | All `/admin-portal/` views | `role in ('employee', 'super_admin')` |
| `@require_super_admin` | `superadmin/views.py` | All `/super-admin/` views | `role == 'super_admin'` + `is_superuser` |
| `IsAuthenticated` | DRF | All booking, payment API views | Django session cookie |
| `AllowAny` | DRF | Search, login, register, webhook | None |
| `IsSuperAdmin` | `accounts/permissions.py` | `CreateEmployeeView` | `role == 'super_admin'` |
| `IsEmployee` | `accounts/permissions.py` | Block/Unblock API | `role in ('employee', 'super_admin')` |

---

## Known Bugs

| # | Severity | File | Lines | Bug | Impact |
|---|----------|------|-------|-----|--------|
| 1 | **High** | `accounts/views.py` | 447–462, 484–499 | `check_login_lock()` returns `bool` but `employee_login_page` and `super_admin_login_page` treat it as `dict` — `lock['locked']` raises `TypeError` | Admin login crashes when lockout threshold is hit |
| 2 | — | `accounts/views.py` | 360 | `LoginView` uses the bool correctly — this is the reference implementation | — |
