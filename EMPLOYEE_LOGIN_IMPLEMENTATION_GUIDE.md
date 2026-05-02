# Employee Login Implementation Guide

## Overview

This guide provides step-by-step instructions for adding employee login to the hotel booking platform. The architecture has been refactored to support this scalable expansion.

---

## Architecture Decision: Option 1 (Recommended)

**Extend existing `accounts` app with user type field**

**Rationale:**
- Shared authentication infrastructure (OTP, email, password hashing)
- Centralized user management
- Easier to maintain
- Simpler permission system
- Reuses existing serializers and backends

---

## Implementation Steps

### Step 1: Update User Model

**File:** `accounts/models.py`

Add user type field to distinguish between customers and employees:

```python
class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model with support for multiple user types.
    
    User Types:
        - customer: Regular hotel booking customers
        - employee: Hotel staff (receptionists, managers, etc.)
        - admin: System administrators
    """

    USER_TYPE_CHOICES = [
        ("customer", "Customer"),
        ("employee", "Employee"),
        ("admin", "Admin"),
    ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email = models.EmailField(
        "email address",
        unique=True,
        db_index=True,
        error_messages={
            "unique": "A user with that email already exists.",
        },
    )
    full_name = models.CharField(
        "full name",
        max_length=150,
    )
    phone = models.CharField(
        "phone number",
        max_length=15,
    )
    user_type = models.CharField(
        "user type",
        max_length=10,
        choices=USER_TYPE_CHOICES,
        default="customer",
        db_index=True,
        help_text="Determines access level and available features.",
    )
    is_active = models.BooleanField(
        "active",
        default=False,
        help_text=(
            "Designates whether this user should be treated as active. "
            "Set to True after OTP email verification."
        ),
    )
    is_staff = models.BooleanField(
        "staff status",
        default=False,
        help_text="Designates whether the user can log into the admin site.",
    )
    date_joined = models.DateTimeField(
        "date joined",
        default=timezone.now,
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["email", "user_type"]),
        ]

    def __str__(self):
        return f"{self.email} ({self.get_user_type_display()})"

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.email

    @property
    def is_customer(self):
        """Check if user is a customer."""
        return self.user_type == "customer"

    @property
    def is_employee(self):
        """Check if user is an employee."""
        return self.user_type == "employee"

    @property
    def is_admin_user(self):
        """Check if user is an admin."""
        return self.user_type == "admin"
```

---

### Step 2: Create Migration

```bash
python manage.py makemigrations accounts
```

**Generated migration will:**
- Add `user_type` field to User model
- Set default value to "customer" for existing users
- Create database index

---

### Step 3: Update Serializers

**File:** `accounts/serializers.py`

Add employee-specific serializers:

```python
class EmployeeRegisterSerializer(serializers.Serializer):
    """
    Validates employee registration input.
    - Requires employee code/ID for verification
    - Same validation as customer registration
    """

    full_name = serializers.CharField(
        max_length=150,
        error_messages={
            "required": "Full name is required.",
            "blank": "Full name cannot be blank.",
        },
    )
    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "invalid": "Enter a valid email address.",
        },
    )
    phone = serializers.CharField(
        max_length=15,
        error_messages={
            "required": "Phone number is required.",
            "blank": "Phone number cannot be blank.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "required": "Password is required.",
            "min_length": "Password must be at least 8 characters long.",
        },
    )
    employee_code = serializers.CharField(
        max_length=50,
        error_messages={
            "required": "Employee code is required.",
        },
    )

    def validate_email(self, value):
        """Check that the email is not already registered."""
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "A user with this email already exists."
            )
        return email

    def validate_phone(self, value):
        """Validate phone number format."""
        phone = value.strip()
        pattern = r"^\+?[\d\-\s]{7,15}$"
        if not re.match(pattern, phone):
            raise serializers.ValidationError(
                "Enter a valid phone number (7-15 digits, optionally starting with +)."
            )
        cleaned = re.sub(r"[^\d+]", "", phone)
        return cleaned

    def validate_password(self, value):
        """Enforce password strength."""
        if len(value) < 8:
            raise serializers.ValidationError(
                "Password must be at least 8 characters long."
            )
        if not re.search(r"[A-Z]", value):
            raise serializers.ValidationError(
                "Password must contain at least one uppercase letter."
            )
        if not re.search(r"[a-z]", value):
            raise serializers.ValidationError(
                "Password must contain at least one lowercase letter."
            )
        if not re.search(r"\d", value):
            raise serializers.ValidationError(
                "Password must contain at least one digit."
            )
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", value):
            raise serializers.ValidationError(
                "Password must contain at least one special character."
            )
        return value

    def validate_employee_code(self, value):
        """Validate employee code against company records."""
        # TODO: Implement employee code validation
        # This should check against a company employee database
        # For now, we'll accept any code
        return value.upper().strip()

    def create(self, validated_data):
        """Create a new employee user."""
        user = User.objects.create_user(
            email=validated_data["email"],
            full_name=validated_data["full_name"],
            phone=validated_data["phone"],
            password=validated_data["password"],
            user_type="employee",  # Set user type to employee
        )
        return user


class EmployeeLoginSerializer(serializers.Serializer):
    """Validates employee login input."""

    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "invalid": "Enter a valid email address.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "Password is required.",
        },
    )

    def validate_email(self, value):
        return value.lower().strip()
```

---

### Step 4: Add Employee Views

**File:** `accounts/views.py`

Add employee-specific views:

```python
class EmployeeRegisterView(APIView):
    """
    POST /accounts/employee/register/

    Register a new employee account.
    - Validates employee code
    - Creates user with user_type="employee"
    - Sends OTP email
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmployeeRegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save employee user
        user = serializer.save()

        # Generate OTP and store in database
        otp_code = create_and_store_otp(user.email)

        # Send OTP email
        email_sent = send_otp_email(user.email, otp_code)

        logger.info("Employee registered: %s — OTP email sent: %s", user.email, email_sent)

        return Response(
            {
                "message": "Employee registration successful. Please check your email for the verification code.",
                "email": user.email,
                "user_type": "employee",
            },
            status=status.HTTP_201_CREATED,
        )


class EmployeeLoginView(APIView):
    """
    POST /accounts/employee/login/

    Authenticate employee with email and password.
    - Same as customer login but for employees
    - Returns employee-specific data
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmployeeLoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        # Check if account is locked
        if check_login_lock(email):
            return Response(
                {
                    "error": "Account temporarily locked due to too many failed attempts. Please try again later.",
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Attempt authentication
        user = authenticate(request, email=email, password=password)

        if user is None:
            record_failed_login(email)
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Check if user is an employee
        if not user.is_employee:
            return Response(
                {
                    "error": "This account is not an employee account.",
                    "code": "NOT_EMPLOYEE",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if user has verified their email
        if not user.is_active:
            return Response(
                {
                    "error": "Your account has not been verified. Please check your email for the verification code.",
                    "code": "ACCOUNT_NOT_VERIFIED",
                    "email": email,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Successful login
        reset_login_attempts(email)
        login(request, user, backend="accounts.backends.EmailBackend")

        logger.info("Employee logged in: %s", email)

        return Response(
            {
                "message": "Login successful.",
                "user": UserSerializer(user).data,
                "user_type": "employee",
            },
            status=status.HTTP_200_OK,
        )


# Page views for employees
def employee_login_page(request):
    """Render the employee login page template."""
    return render(request, "accounts/employee_login.html")


def employee_register_page(request):
    """Render the employee registration page template."""
    return render(request, "accounts/employee_register.html")
```

---

### Step 5: Update URLs

**File:** `accounts/urls.py`

Add employee routes:

```python
"""
URL configuration for the accounts app.

Routes:
    Customer Pages:
        /accounts/login/page/               — Customer login page
        /accounts/register/page/            — Customer registration page
    
    Employee Pages:
        /accounts/employee/login/page/      — Employee login page
        /accounts/employee/register/page/   — Employee registration page
    
    Customer API:
        POST /accounts/register/            — Register customer
        POST /accounts/verify-otp/          — Verify OTP
        POST /accounts/resend-otp/          — Resend OTP
        POST /accounts/login/               — Customer login
        POST /accounts/logout/              — Logout
        GET  /accounts/me/                  — Get current user
    
    Employee API:
        POST /accounts/employee/register/   — Register employee
        POST /accounts/employee/login/      — Employee login
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Customer page views
    path("login/page/", views.login_page, name="login-page"),
    path("register/page/", views.register_page, name="register-page"),

    # Employee page views
    path("employee/login/page/", views.employee_login_page, name="employee-login-page"),
    path("employee/register/page/", views.employee_register_page, name="employee-register-page"),

    # Customer API endpoints
    path("register/", views.RegisterView.as_view(), name="register"),
    path("verify-otp/", views.VerifyOTPView.as_view(), name="verify-otp"),
    path("resend-otp/", views.ResendOTPView.as_view(), name="resend-otp"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.CurrentUserView.as_view(), name="me"),

    # Employee API endpoints
    path("employee/register/", views.EmployeeRegisterView.as_view(), name="employee-register"),
    path("employee/login/", views.EmployeeLoginView.as_view(), name="employee-login"),
]
```

---

### Step 6: Create Employee Templates

**File:** `templates/accounts/employee_login.html`

```html
{% extends "base.html" %}

{% block title %}Employee Login - Hotel Booking{% endblock %}

{% block content %}
<div class="container">
    <div class="login-form">
        <h1>Employee Login</h1>
        <form id="employee-login-form">
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" required>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary">Login</button>
        </form>
        <p>Don't have an account? <a href="{% url 'accounts:employee-register-page' %}">Register here</a></p>
    </div>
</div>

<script>
    document.getElementById('employee-login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        
        try {
            const response = await fetch('/accounts/employee/login/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({ email, password }),
            });
            
            const data = await response.json();
            
            if (response.ok) {
                // Redirect to employee dashboard
                window.location.href = '/employee/dashboard/';
            } else {
                alert(data.error || 'Login failed');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred. Please try again.');
        }
    });
</script>
{% endblock %}
```

**File:** `templates/accounts/employee_register.html`

```html
{% extends "base.html" %}

{% block title %}Employee Registration - Hotel Booking{% endblock %}

{% block content %}
<div class="container">
    <div class="register-form">
        <h1>Employee Registration</h1>
        <form id="employee-register-form">
            <div class="form-group">
                <label for="full_name">Full Name</label>
                <input type="text" id="full_name" name="full_name" required>
            </div>
            <div class="form-group">
                <label for="email">Email</label>
                <input type="email" id="email" name="email" required>
            </div>
            <div class="form-group">
                <label for="phone">Phone</label>
                <input type="tel" id="phone" name="phone" required>
            </div>
            <div class="form-group">
                <label for="employee_code">Employee Code</label>
                <input type="text" id="employee_code" name="employee_code" required>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary">Register</button>
        </form>
        <p>Already have an account? <a href="{% url 'accounts:employee-login-page' %}">Login here</a></p>
    </div>
</div>

<script>
    document.getElementById('employee-register-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const formData = {
            full_name: document.getElementById('full_name').value,
            email: document.getElementById('email').value,
            phone: document.getElementById('phone').value,
            employee_code: document.getElementById('employee_code').value,
            password: document.getElementById('password').value,
        };
        
        try {
            const response = await fetch('/accounts/employee/register/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify(formData),
            });
            
            const data = await response.json();
            
            if (response.ok) {
                alert('Registration successful! Please check your email for the verification code.');
                window.location.href = '/accounts/verify-otp/page/';
            } else {
                alert(data.errors ? JSON.stringify(data.errors) : 'Registration failed');
            }
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred. Please try again.');
        }
    });
</script>
{% endblock %}
```

---

### Step 7: Update Admin

**File:** `accounts/admin.py`

Add employee filtering:

```python
from django.contrib import admin
from .models import User, OTP, LoginAttempt

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'full_name', 'user_type', 'is_active', 'date_joined']
    list_filter = ['user_type', 'is_active', 'date_joined']
    search_fields = ['email', 'full_name']
    readonly_fields = ['id', 'date_joined']
    
    fieldsets = (
        ('Personal Info', {
            'fields': ('id', 'email', 'full_name', 'phone')
        }),
        ('Account Type', {
            'fields': ('user_type',)
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Dates', {
            'fields': ('date_joined',)
        }),
    )
```

---

### Step 8: Create Permissions/Decorators

**File:** `accounts/permissions.py` (New file)

```python
"""
Custom permissions for different user types.
"""

from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    """Allow access only to customer users."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_customer


class IsEmployee(BasePermission):
    """Allow access only to employee users."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_employee


class IsAdminUser(BasePermission):
    """Allow access only to admin users."""
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_admin_user
```

---

### Step 9: Update Existing Views with Permissions

**File:** `rooms/views.py`

Add customer-only permission to booking views:

```python
from accounts.permissions import IsCustomer

class HoldRoomView(APIView):
    """Hold a room for booking."""
    permission_classes = [IsAuthenticated, IsCustomer]
    # ... rest of view

class ProcessPaymentView(APIView):
    """Process payment for booking."""
    permission_classes = [IsAuthenticated, IsCustomer]
    # ... rest of view

class CancelBookingView(APIView):
    """Cancel a booking."""
    permission_classes = [IsAuthenticated, IsCustomer]
    # ... rest of view
```

---

## Implementation Checklist

- [ ] Update User model with `user_type` field
- [ ] Create and run migration
- [ ] Add employee serializers
- [ ] Add employee views
- [ ] Update URLs with employee routes
- [ ] Create employee templates
- [ ] Update admin configuration
- [ ] Create permissions module
- [ ] Update existing views with permissions
- [ ] Test employee registration
- [ ] Test employee login
- [ ] Test OTP verification for employees
- [ ] Test permission restrictions

---

## Testing Employee Login

### 1. Register Employee
```bash
curl -X POST http://localhost:8000/accounts/employee/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "John Doe",
    "email": "john@hotel.com",
    "phone": "+1234567890",
    "employee_code": "EMP001",
    "password": "SecurePass123!"
  }'
```

### 2. Verify OTP
```bash
curl -X POST http://localhost:8000/accounts/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@hotel.com",
    "otp": "123456"
  }'
```

### 3. Login Employee
```bash
curl -X POST http://localhost:8000/accounts/employee/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@hotel.com",
    "password": "SecurePass123!"
  }'
```

---

## Future Enhancements

1. **Employee Dashboard** - Create employee-specific views
2. **Role-Based Access** - Add roles (receptionist, manager, etc.)
3. **Employee Permissions** - Restrict access to specific features
4. **Audit Logging** - Track employee actions
5. **Employee Management** - Admin interface for managing employees
6. **Shift Management** - Track employee shifts and availability

---

## Summary

The architecture is now ready for employee login implementation. The refactored MVT structure ensures:

✅ Clean separation of concerns
✅ Scalable user type system
✅ Reusable authentication infrastructure
✅ Easy permission management
✅ Maintainable codebase

**Estimated Implementation Time:** 4-6 hours
**Complexity Level:** Medium
**Risk Level:** Low (no breaking changes to existing code)
