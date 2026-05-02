# Verification Checklist - Django Architecture Refactoring

## Pre-Deployment Verification

Run these checks before deploying to production:

### 1. Django System Check
```bash
python manage.py check
```

**Expected Output:**
```
System check identified no issues (0 silenced).
```

---

### 2. Run Migrations
```bash
python manage.py migrate
```

**Expected Output:**
```
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, sessions, accounts, rooms, payments
Running migrations:
  Applying ... OK
```

---

### 3. Test All Routes

Start the development server:
```bash
python manage.py runserver
```

#### Page Routes
- [ ] `http://localhost:8000/` → Home page loads
- [ ] `http://localhost:8000/accounts/login/page/` → Login page loads
- [ ] `http://localhost:8000/accounts/register/page/` → Register page loads
- [ ] `http://localhost:8000/rooms/search/page/` → Search page loads
- [ ] `http://localhost:8000/rooms/room/page/` → Room detail page loads
- [ ] `http://localhost:8000/bookings/my-bookings/page/` → My bookings page loads
- [ ] `http://localhost:8000/bookings/confirmation/page/` → Confirmation page loads
- [ ] `http://localhost:8000/payments/checkout/page/` → Checkout page loads

#### API Routes (Test with curl or Postman)
- [ ] `POST /accounts/register/` → Returns 400 (validation error expected)
- [ ] `POST /accounts/login/` → Returns 400 (validation error expected)
- [ ] `GET /accounts/me/` → Returns 401 (not authenticated)
- [ ] `GET /rooms/search/` → Returns 400 (missing parameters)
- [ ] `POST /bookings/hold/` → Returns 401 (not authenticated)

---

### 4. Check File Structure

Verify all files are in correct locations:

```bash
# Check core app exists
ls -la core/
# Should show: __init__.py, apps.py, views.py, urls.py

# Check accounts views has page views
grep -n "def login_page" accounts/views.py
grep -n "def register_page" accounts/views.py

# Check accounts urls has no view logic
grep -n "def " accounts/urls.py
# Should return nothing (no function definitions)

# Check rooms views has page views
grep -n "def search_page" rooms/views.py
grep -n "def room_detail_page" rooms/views.py
grep -n "def my_bookings_page" rooms/views.py
grep -n "def confirmation_page" rooms/views.py

# Check rooms urls has no view logic
grep -n "def " rooms/urls.py
# Should return nothing

# Check payments views has page view
grep -n "def checkout_page" payments/views.py

# Check payments urls has no view logic
grep -n "def " payments/urls.py
# Should return nothing
```

---

### 5. Import Verification

Check that all imports are correct:

```bash
# Check for render imports in views.py files
grep -n "from django.shortcuts import render" accounts/views.py
grep -n "from django.shortcuts import render" rooms/views.py
grep -n "from django.shortcuts import render" payments/views.py
grep -n "from django.shortcuts import render" core/views.py

# Check that urls.py files don't import render
grep -n "from django.shortcuts import render" accounts/urls.py
# Should return nothing

grep -n "from django.shortcuts import render" rooms/urls.py
# Should return nothing

grep -n "from django.shortcuts import render" payments/urls.py
# Should return nothing

grep -n "from django.shortcuts import render" hotel_booking/urls.py
# Should return nothing
```

---

### 6. Settings Verification

Check that core app is in INSTALLED_APPS:

```bash
grep -A 15 "INSTALLED_APPS = " hotel_booking/settings.py | grep "core"
# Should show: "core",
```

---

### 7. URL Configuration Verification

Check that all URL patterns are correct:

```bash
# Check core urls
grep -n "path" core/urls.py
# Should show: path("", views.home_page, name="home"),

# Check accounts urls
grep -n "path" accounts/urls.py
# Should show page and API routes

# Check rooms urls
grep -n "path" rooms/urls.py
# Should show page and API routes

# Check payments urls
grep -n "path" payments/urls.py
# Should show page and API routes

# Check main urls
grep -n "include" hotel_booking/urls.py
# Should show: include("core.urls"), include("accounts.urls"), etc.
```

---

### 8. Syntax Check

Run Python syntax check:

```bash
python -m py_compile core/views.py
python -m py_compile core/urls.py
python -m py_compile accounts/views.py
python -m py_compile accounts/urls.py
python -m py_compile rooms/views.py
python -m py_compile rooms/urls.py
python -m py_compile rooms/booking_urls.py
python -m py_compile payments/views.py
python -m py_compile payments/urls.py
python -m py_compile hotel_booking/urls.py
python -m py_compile hotel_booking/settings.py
```

**Expected Output:** No errors

---

### 9. Test API Endpoints

#### Register User
```bash
curl -X POST http://localhost:8000/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Test User",
    "email": "test@example.com",
    "phone": "+1234567890",
    "password": "TestPass123!"
  }'
```

**Expected:** 201 Created or 400 Bad Request (if email exists)

#### Search Rooms
```bash
curl -X GET "http://localhost:8000/rooms/search/?city=Mumbai&check_in=2026-05-01&check_out=2026-05-03&guests=2"
```

**Expected:** 200 OK with room list

#### Get Current User
```bash
curl -X GET http://localhost:8000/accounts/me/ \
  -H "Cookie: sessionid=YOUR_SESSION_ID"
```

**Expected:** 200 OK (if authenticated) or 401 Unauthorized (if not)

---

### 10. Admin Interface

- [ ] Navigate to `http://localhost:8000/admin/`
- [ ] Login with superuser credentials
- [ ] Check that all apps are visible:
  - [ ] Accounts (Users, OTPs, Login Attempts)
  - [ ] Rooms (Rooms, Room Images, Bookings)
  - [ ] Payments (Payments)
- [ ] Verify no errors in admin interface

---

### 11. Static Files

```bash
python manage.py collectstatic --noinput
```

**Expected:** Static files collected successfully

---

### 12. Database Integrity

```bash
python manage.py dbshell
```

**Check tables exist:**
```sql
.tables
-- Should show: accounts_user, accounts_otp, accounts_loginattempt, rooms_room, rooms_roomimage, rooms_booking, payments_payment, etc.
```

---

### 13. Code Quality

Run linting (if installed):

```bash
# If flake8 is installed
flake8 core/ accounts/ rooms/ payments/ hotel_booking/

# If pylint is installed
pylint core/ accounts/ rooms/ payments/ hotel_booking/
```

---

### 14. Performance Check

Check for N+1 queries in views:

```bash
# Enable query logging in settings.py (development only)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

Then test endpoints and check query count.

---

### 15. Security Check

- [ ] DEBUG = False in production
- [ ] SECRET_KEY is set in environment
- [ ] ALLOWED_HOSTS is configured
- [ ] CSRF protection is enabled
- [ ] Session cookies are secure
- [ ] HTTPS is enforced (in production)

---

## Automated Test Script

Create `verify_refactoring.sh`:

```bash
#!/bin/bash

echo "=== Django Architecture Refactoring Verification ==="
echo ""

echo "1. Checking Django system..."
python manage.py check
if [ $? -ne 0 ]; then
    echo "❌ Django check failed"
    exit 1
fi
echo "✅ Django check passed"
echo ""

echo "2. Checking file structure..."
if [ ! -f "core/views.py" ]; then
    echo "❌ core/views.py not found"
    exit 1
fi
echo "✅ core/views.py exists"

if [ ! -f "core/urls.py" ]; then
    echo "❌ core/urls.py not found"
    exit 1
fi
echo "✅ core/urls.py exists"
echo ""

echo "3. Checking for view logic in urls.py files..."
if grep -q "^def " accounts/urls.py; then
    echo "❌ accounts/urls.py contains function definitions"
    exit 1
fi
echo "✅ accounts/urls.py is clean"

if grep -q "^def " rooms/urls.py; then
    echo "❌ rooms/urls.py contains function definitions"
    exit 1
fi
echo "✅ rooms/urls.py is clean"

if grep -q "^def " payments/urls.py; then
    echo "❌ payments/urls.py contains function definitions"
    exit 1
fi
echo "✅ payments/urls.py is clean"
echo ""

echo "4. Checking for page views in views.py files..."
if ! grep -q "def login_page" accounts/views.py; then
    echo "❌ login_page not found in accounts/views.py"
    exit 1
fi
echo "✅ login_page found in accounts/views.py"

if ! grep -q "def search_page" rooms/views.py; then
    echo "❌ search_page not found in rooms/views.py"
    exit 1
fi
echo "✅ search_page found in rooms/views.py"

if ! grep -q "def checkout_page" payments/views.py; then
    echo "❌ checkout_page not found in payments/views.py"
    exit 1
fi
echo "✅ checkout_page found in payments/views.py"
echo ""

echo "5. Checking settings..."
if ! grep -q '"core"' hotel_booking/settings.py; then
    echo "❌ core app not in INSTALLED_APPS"
    exit 1
fi
echo "✅ core app in INSTALLED_APPS"
echo ""

echo "=== All Checks Passed ✅ ==="
echo ""
echo "Next steps:"
echo "1. Run: python manage.py migrate"
echo "2. Run: python manage.py runserver"
echo "3. Test all routes in browser"
echo "4. Test API endpoints with curl/Postman"
```

Run it:
```bash
chmod +x verify_refactoring.sh
./verify_refactoring.sh
```

---

## Troubleshooting

### Issue: "No module named 'core'"
**Solution:** Make sure `core` is in `INSTALLED_APPS` in settings.py

### Issue: "Page not found" for page routes
**Solution:** Check that `include("core.urls")` is in `hotel_booking/urls.py`

### Issue: Import errors in views.py
**Solution:** Make sure `from django.shortcuts import render` is imported

### Issue: URL routing not working
**Solution:** Run `python manage.py check` to see specific errors

### Issue: Admin interface not showing core app
**Solution:** Create `core/admin.py` if needed, or restart Django server

---

## Sign-Off

- [ ] All checks passed
- [ ] No errors in Django system check
- [ ] All routes tested and working
- [ ] API endpoints responding correctly
- [ ] Admin interface functional
- [ ] Static files collected
- [ ] Database integrity verified
- [ ] Code quality acceptable
- [ ] Security settings configured
- [ ] Ready for production deployment

---

## Deployment Checklist

Before deploying to production:

- [ ] Run all verification checks
- [ ] Set DEBUG = False
- [ ] Configure ALLOWED_HOSTS
- [ ] Set SECRET_KEY from environment
- [ ] Configure email settings
- [ ] Configure Razorpay keys
- [ ] Run migrations on production database
- [ ] Collect static files
- [ ] Test all critical user flows
- [ ] Monitor error logs
- [ ] Have rollback plan ready

---

**Verification Status: READY ✅**
