# Django Architecture Diagram

## Project Structure (After Refactoring)

```
hotel_booking/
│
├── core/                           ← NEW: Core pages app
│   ├── __init__.py
│   ├── apps.py
│   ├── views.py                    ✅ home_page()
│   └── urls.py                     ✅ Only routes
│
├── accounts/                       ← User authentication
│   ├── models.py                   ✅ User, OTP, LoginAttempt
│   ├── views.py                    ✅ login_page(), register_page(), API views
│   ├── urls.py                     ✅ Only routes (NO view logic)
│   ├── serializers.py              ✅ Input validation
│   ├── backends.py                 ✅ Email authentication
│   ├── utils.py                    ✅ OTP, email helpers
│   ├── admin.py                    ✅ Admin configuration
│   ├── managers.py                 ✅ Custom user manager
│   └── migrations/
│
├── rooms/                          ← Room search & bookings
│   ├── models.py                   ✅ Room, RoomImage, Booking
│   ├── views.py                    ✅ search_page(), room_detail_page(), my_bookings_page(), confirmation_page(), API views
│   ├── urls.py                     ✅ Only routes (NO view logic)
│   ├── booking_urls.py             ✅ Only routes (NO view logic)
│   ├── serializers.py              ✅ Room, Booking serializers
│   ├── admin.py                    ✅ Admin configuration
│   ├── management/
│   │   └── commands/
│   │       └── seed_rooms.py       ✅ Data seeding
│   └── migrations/
│
├── payments/                       ← Razorpay integration
│   ├── models.py                   ✅ Payment model
│   ├── views.py                    ✅ checkout_page(), API views
│   ├── urls.py                     ✅ Only routes (NO view logic)
│   ├── serializers.py              ✅ Payment serializers
│   ├── utils.py                    ✅ Razorpay helpers
│   ├── admin.py                    ✅ Admin configuration
│   └── migrations/
│
├── hotel_booking/                  ← Project configuration
│   ├── settings.py                 ✅ Updated with core app
│   ├── urls.py                     ✅ Cleaned up (NO view logic)
│   ├── wsgi.py
│   ├── asgi.py
│   └── dashboard.py
│
├── templates/                      ← HTML templates
│   ├── base.html
│   ├── pages/
│   │   └── index.html
│   ├── accounts/
│   │   ├── login.html
│   │   └── register.html
│   ├── rooms/
│   │   ├── search.html
│   │   └── room_details.html
│   ├── bookings/
│   │   ├── my_bookings.html
│   │   └── confirmation.html
│   ├── payments/
│   │   └── checkout.html
│   ├── admin/
│   │   └── base_site.html
│   └── emails/
│       ├── otp_email.html
│       └── booking_confirmation.html
│
├── static/                         ← Static assets
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── auth.js
│   └── images/
│       └── room-hero.png
│
├── media/                          ← User uploads
│   └── room_images/
│
├── manage.py
├── requirements.txt
└── db.sqlite3
```

---

## Request Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    HTTP Request/Response
                             │
        ┌────────────────────┴────────────────────┐
        │                                         │
        ▼                                         ▼
   ┌─────────────┐                         ┌──────────────┐
   │ Page Routes │                         │ API Routes   │
   │ (HTML)      │                         │ (JSON)       │
   └──────┬──────┘                         └──────┬───────┘
          │                                       │
          │ GET /                                 │ POST /accounts/register/
          │ GET /accounts/login/page/            │ POST /accounts/login/
          │ GET /rooms/search/page/              │ GET  /rooms/search/
          │ GET /bookings/my-bookings/page/      │ POST /bookings/hold/
          │ GET /payments/checkout/page/         │ POST /payments/create-order/
          │                                       │
          ▼                                       ▼
    ┌──────────────────────────────────────────────────────┐
    │              DJANGO URL ROUTER                       │
    │  (hotel_booking/urls.py)                             │
    │                                                      │
    │  path("", include("core.urls"))                      │
    │  path("accounts/", include("accounts.urls"))         │
    │  path("rooms/", include("rooms.urls"))               │
    │  path("bookings/", include("rooms.booking_urls"))    │
    │  path("payments/", include("payments.urls"))         │
    └──────────────────────────────────────────────────────┘
          │                                       │
          ▼                                       ▼
    ┌──────────────────────┐            ┌──────────────────────┐
    │   PAGE VIEWS         │            │   API VIEWS          │
    │  (views.py)          │            │  (views.py)          │
    │                      │            │                      │
    │ home_page()          │            │ RegisterView         │
    │ login_page()         │            │ LoginView            │
    │ search_page()        │            │ SearchRoomsView      │
    │ room_detail_page()   │            │ HoldRoomView         │
    │ my_bookings_page()   │            │ CreateOrderView      │
    │ confirmation_page()  │            │ VerifyPaymentView    │
    │ checkout_page()      │            │ WebhookView          │
    └──────────┬───────────┘            └──────────┬───────────┘
               │                                   │
               │ render()                          │ JSON response
               │                                   │
               ▼                                   ▼
        ┌─────────────────┐              ┌──────────────────┐
        │  SERIALIZERS    │              │  SERIALIZERS     │
        │  (serializers.py)              │  (serializers.py)│
        │                 │              │                  │
        │ (Data passed    │              │ RegisterSerializer
        │  to template)   │              │ LoginSerializer
        │                 │              │ SearchSerializer
        └────────┬────────┘              │ BookingSerializer
                 │                       └────────┬─────────┘
                 │                                │
                 ▼                                ▼
        ┌─────────────────┐              ┌──────────────────┐
        │  TEMPLATES      │              │  MODELS          │
        │  (templates/)   │              │  (models.py)     │
        │                 │              │                  │
        │ base.html       │              │ User             │
        │ index.html      │              │ Room             │
        │ login.html      │              │ Booking          │
        │ search.html     │              │ Payment          │
        │ room_details.html              │ OTP              │
        │ my_bookings.html               │ LoginAttempt     │
        │ confirmation.html              └────────┬─────────┘
        │ checkout.html   │                       │
        └────────┬────────┘              ┌────────▼─────────┐
                 │                       │   DATABASE       │
                 │                       │   (SQLite/       │
                 │                       │    PostgreSQL)   │
                 │                       └──────────────────┘
                 │
                 ▼
        ┌─────────────────┐
        │  HTML Response  │
        │  (Browser)      │
        └─────────────────┘
```

---

## MVT Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Templates (HTML)                                        │   │
│  │  - base.html, index.html, login.html, search.html, etc. │   │
│  │  - Rendered by page views                               │   │
│  │  - Receives context data from views                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                             ▲
                             │
                    render(template, context)
                             │
┌─────────────────────────────────────────────────────────────────┐
│                    BUSINESS LOGIC LAYER                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Views (views.py)                                        │   │
│  │  - Page Views: login_page(), search_page(), etc.        │   │
│  │  - API Views: RegisterView, SearchRoomsView, etc.       │   │
│  │  - Handle requests, process data, return responses      │   │
│  │  - Call serializers for validation                      │   │
│  │  - Call models for database operations                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Serializers (serializers.py)                            │   │
│  │  - Validate input data                                  │   │
│  │  - Transform data for API responses                     │   │
│  │  - Handle data serialization/deserialization            │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Utils (utils.py)                                        │   │
│  │  - OTP generation and verification                      │   │
│  │  - Email sending                                        │   │
│  │  - Razorpay integration                                 │   │
│  │  - Helper functions                                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                             ▲
                             │
                    Model operations
                             │
┌─────────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Models (models.py)                                      │   │
│  │  - User, Room, Booking, Payment, OTP, LoginAttempt      │   │
│  │  - Define database schema                               │   │
│  │  - Contain business logic (properties, methods)          │   │
│  │  - Enforce data validation                              │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Database (SQLite/PostgreSQL)                            │   │
│  │  - Persistent data storage                              │   │
│  │  - Tables for each model                                │   │
│  │  - Relationships and constraints                        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## URL Routing Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DJANGO URL ROUTER                            │
│                  (hotel_booking/urls.py)                        │
└─────────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
   ┌─────────┐          ┌──────────┐        ┌──────────┐
   │ core/   │          │accounts/ │        │ rooms/   │
   │urls.py  │          │urls.py   │        │urls.py   │
   └────┬────┘          └────┬─────┘        └────┬─────┘
        │                    │                    │
        │ path("", ...)      │ path("login/page/", ...)
        │                    │ path("register/page/", ...)
        │                    │ path("register/", ...)
        │                    │ path("login/", ...)
        │                    │
        ▼                    ▼                    ▼
   ┌─────────────┐      ┌──────────────┐    ┌──────────────┐
   │ core/views  │      │accounts/views│    │ rooms/views  │
   │             │      │              │    │              │
   │ home_page() │      │login_page()  │    │search_page() │
   │             │      │register_page()    │room_detail_  │
   │             │      │RegisterView  │    │page()        │
   │             │      │LoginView     │    │SearchRoomsView
   │             │      │VerifyOTPView │    │RoomDetailView
   │             │      │              │    │              │
   └─────────────┘      └──────────────┘    └──────────────┘
        │                    │                    │
        │ render()           │ JSON response      │ render()
        │                    │                    │
        ▼                    ▼                    ▼
   ┌─────────────┐      ┌──────────────┐    ┌──────────────┐
   │ HTML        │      │ JSON         │    │ HTML         │
   │ Response    │      │ Response     │    │ Response     │
   └─────────────┘      └──────────────┘    └──────────────┘
```

---

## Data Flow: User Registration

```
┌──────────────────────────────────────────────────────────────────┐
│                    USER REGISTRATION FLOW                        │
└──────────────────────────────────────────────────────────────────┘

1. USER SUBMITS FORM
   ┌─────────────────────────────────────────┐
   │ Browser: POST /accounts/register/       │
   │ Data: {email, full_name, phone, pwd}    │
   └────────────────┬────────────────────────┘
                    │
                    ▼
2. URL ROUTING
   ┌─────────────────────────────────────────┐
   │ accounts/urls.py                        │
   │ path("register/", RegisterView.as_view())
   └────────────────┬────────────────────────┘
                    │
                    ▼
3. VIEW PROCESSING
   ┌─────────────────────────────────────────┐
   │ accounts/views.py: RegisterView         │
   │ - Validate input with serializer        │
   │ - Create user in database               │
   │ - Generate OTP                          │
   │ - Send OTP email                        │
   └────────────────┬────────────────────────┘
                    │
                    ▼
4. SERIALIZER VALIDATION
   ┌─────────────────────────────────────────┐
   │ accounts/serializers.py                 │
   │ RegisterSerializer.validate()           │
   │ - Check email not duplicate             │
   │ - Validate phone format                 │
   │ - Check password strength               │
   └────────────────┬────────────────────────┘
                    │
                    ▼
5. MODEL CREATION
   ┌─────────────────────────────────────────┐
   │ accounts/models.py: User.objects.create_user()
   │ - Hash password with bcrypt             │
   │ - Create user record                    │
   │ - Set is_active=False                   │
   └────────────────┬────────────────────────┘
                    │
                    ▼
6. DATABASE STORAGE
   ┌─────────────────────────────────────────┐
   │ Database: INSERT INTO accounts_user     │
   │ - id, email, full_name, phone, password │
   │ - is_active, date_joined                │
   └────────────────┬────────────────────────┘
                    │
                    ▼
7. OTP GENERATION & EMAIL
   ┌─────────────────────────────────────────┐
   │ accounts/utils.py                       │
   │ - Generate 6-digit OTP                  │
   │ - Store in OTP table                    │
   │ - Send email via Gmail SMTP             │
   └────────────────┬────────────────────────┘
                    │
                    ▼
8. RESPONSE
   ┌─────────────────────────────────────────┐
   │ Browser: 201 Created                    │
   │ {message, email}                        │
   └─────────────────────────────────────────┘
```

---

## App Dependencies

```
┌─────────────────────────────────────────────────────────────────┐
│                    APP DEPENDENCIES                             │
└─────────────────────────────────────────────────────────────────┘

core
  └─ No dependencies

accounts
  ├─ models.py (User, OTP, LoginAttempt)
  ├─ views.py (uses models, serializers, utils)
  ├─ serializers.py (uses models)
  ├─ utils.py (uses models, settings)
  ├─ backends.py (uses models)
  └─ admin.py (uses models)

rooms
  ├─ models.py (Room, RoomImage, Booking)
  │  └─ Booking.user → accounts.User
  ├─ views.py (uses models, serializers, utils)
  ├─ serializers.py (uses models)
  ├─ admin.py (uses models)
  └─ management/commands/seed_rooms.py (uses models)

payments
  ├─ models.py (Payment)
  │  └─ Payment.booking → rooms.Booking
  ├─ views.py (uses models, serializers, utils)
  ├─ serializers.py (uses models)
  ├─ utils.py (uses models, settings)
  └─ admin.py (uses models)

hotel_booking (project config)
  ├─ settings.py (configures all apps)
  ├─ urls.py (includes all app urls)
  ├─ wsgi.py
  └─ asgi.py
```

---

## File Organization Summary

```
✅ CORRECT ORGANIZATION:

accounts/
├── models.py          ← Database schema
├── views.py           ← Request handlers (page + API)
├── urls.py            ← Route definitions ONLY
├── serializers.py     ← Data validation
├── utils.py           ← Helper functions
├── backends.py        ← Authentication logic
├── admin.py           ← Admin configuration
└── migrations/        ← Database migrations

❌ WRONG ORGANIZATION (BEFORE):

accounts/
├── models.py
├── views.py           ← Only API views
├── urls.py            ← Contains view logic ❌
│   ├── def login_page()
│   ├── def register_page()
│   └── urlpatterns
├── serializers.py
├── utils.py
├── backends.py
├── admin.py
└── migrations/
```

---

## Summary

The refactored architecture now properly separates concerns:

- **URLs** contain only route definitions
- **Views** contain all request handling logic
- **Models** contain data schema and business logic
- **Serializers** handle data validation
- **Utils** contain helper functions
- **Templates** contain presentation logic
- **Admin** contains admin configuration

This follows Django MVT best practices and is ready for production deployment and future enhancements like employee login.
