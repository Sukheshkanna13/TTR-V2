"""
API views for the accounts app.

3-Step Registration Flow (no ghost users in DB):
  Step 1: POST /accounts/register/       — name + email + phone → store in PendingRegistration, send OTP
  Step 2: POST /accounts/verify-otp/     — email + otp → mark email_verified=True on PendingRegistration
  Step 3: POST /accounts/set-password/   — email + password → create real User, delete PendingRegistration, log in

Only after Step 3 is a User row written to the database.
"""

import logging
import secrets

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import redirect, render
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_q.tasks import async_task

from .models import PendingRegistration
from .permissions import IsSuperAdmin
from .serializers import (
    InitiateRegistrationSerializer,
    LoginSerializer,
    ResendOTPSerializer,
    SetPasswordSerializer,
    UserSerializer,
    VerifyOTPSerializer,
    EmployeeCreationSerializer,
)
from .utils import (
    check_login_lock,
    create_and_store_otp,
    record_failed_login,
    reset_login_attempts,
    send_otp_email,
    verify_otp,
)

User = get_user_model()
logger = logging.getLogger(__name__)


# =============================================================================
# STEP 1 — Initiate Registration
# =============================================================================

class RegisterView(APIView):
    """
    POST /accounts/register/

    Step 1 of registration. Accepts name, email, phone — NO password.
    - Checks for existing active account
    - Stores data in PendingRegistration (not User table)
    - Sends OTP to email
    - Returns 201
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = InitiateRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        full_name = serializer.validated_data["full_name"]
        phone = serializer.validated_data["phone"]

        # Upsert the pending record (allow re-registration if previous attempt expired or unverified)
        PendingRegistration.objects.filter(email=email).delete()
        pending = PendingRegistration.objects.create(
            email=email,
            full_name=full_name,
            phone=phone,
        )

        # Send OTP
        otp_code = create_and_store_otp(email)
        email_sent = send_otp_email(email, otp_code)

        logger.info("Registration initiated for %s — OTP sent: %s", email, email_sent)

        return Response(
            {
                "message": "Verification code sent to your email. Please enter it to continue.",
                "email": email,
                "next_step": "verify-otp",
            },
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# STEP 2 — Verify OTP
# =============================================================================

class VerifyOTPView(APIView):
    """
    POST /accounts/verify-otp/

    Step 2 of registration (or standalone email verification for login flow).
    - Verifies OTP against the database
    - If from a PendingRegistration → marks email_verified=True, prompts for password
    - If from an existing unverified User (legacy) → activates user and logs in
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        submitted_otp = serializer.validated_data["otp"]

        # Verify OTP
        result = verify_otp(email, submitted_otp)

        if not result["success"]:
            code = result["code"]
            if code == "OTP_BLOCKED":
                http_status = status.HTTP_429_TOO_MANY_REQUESTS
            elif code == "OTP_EXPIRED":
                http_status = status.HTTP_410_GONE
            else:
                http_status = status.HTTP_400_BAD_REQUEST
            return Response({"error": result["error"], "code": code}, status=http_status)

        # ── Case A: New signup via PendingRegistration ──
        try:
            pending = PendingRegistration.objects.get(email=email)
            if pending.is_expired:
                pending.delete()
                return Response(
                    {
                        "error": "Your registration session has expired. Please start again.",
                        "code": "SESSION_EXPIRED",
                    },
                    status=status.HTTP_410_GONE,
                )
            pending.email_verified = True
            pending.save(update_fields=["email_verified"])

            logger.info("Email verified (pending registration): %s", email)
            return Response(
                {
                    "message": "Email verified! Please create a password to complete your account.",
                    "email": email,
                    "next_step": "set-password",
                },
                status=status.HTTP_200_OK,
            )
        except PendingRegistration.DoesNotExist:
            pass

        # ── Case B: Existing unverified User (legacy / admin-created) ──
        try:
            user = User.objects.get(email=email)
            if user.is_active:
                return Response(
                    {"error": "This account is already verified. Please log in."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.is_active = True
            user.save(update_fields=["is_active"])
            login(request, user, backend="accounts.backends.EmailBackend")
            logger.info("Existing user verified and logged in: %s", email)
            return Response(
                {"message": "Email verified. You are now logged in.", "user": UserSerializer(user).data},
                status=status.HTTP_200_OK,
            )
        except User.DoesNotExist:
            pass

        return Response(
            {"error": "No matching registration found for this email."},
            status=status.HTTP_404_NOT_FOUND,
        )


# =============================================================================
# STEP 3 — Set Password & Complete Registration
# =============================================================================

class SetPasswordView(APIView):
    """
    POST /accounts/set-password/

    Step 3 of registration. Only reachable after OTP is verified.
    - Validates password strength
    - Creates the real User row
    - Deletes PendingRegistration
    - Logs the user in (Django session)
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        # Fetch the pending record
        try:
            pending = PendingRegistration.objects.get(email=email)
        except PendingRegistration.DoesNotExist:
            return Response(
                {
                    "error": "No pending registration found. Please start registration again.",
                    "code": "NO_PENDING_REGISTRATION",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if pending.is_expired:
            pending.delete()
            return Response(
                {
                    "error": "Your registration session has expired. Please start again.",
                    "code": "SESSION_EXPIRED",
                },
                status=status.HTTP_410_GONE,
            )

        if not pending.email_verified:
            return Response(
                {
                    "error": "Email not yet verified. Please complete OTP verification first.",
                    "code": "EMAIL_NOT_VERIFIED",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard: if a user already exists with this email
        # If they are already active, they must log in.
        # If they are NOT active (ghost/legacy), we update them and complete registration.
        existing_user = User.objects.filter(email=email).first()
        if existing_user and existing_user.is_active:
            pending.delete()
            return Response(
                {"error": "An account with this email already exists and is active. Please log in."},
                status=status.HTTP_409_CONFLICT,
            )

        if existing_user:
            # Adopt existing unverified user
            user = existing_user
            user.full_name = pending.full_name
            user.phone = pending.phone
            user.set_password(password)
            user.is_active = True
            user.save()
            logger.info("Existing unverified user '%s' adopted and activated via registration flow.", email)
        else:
            # Create a brand new User
            user = User.objects.create_user(
                email=pending.email,
                full_name=pending.full_name,
                phone=pending.phone,
                password=password,
            )
            user.is_active = True
            user.save(update_fields=["is_active"])
            logger.info("New user '%s' created and activated.", email)

        # Clean up pending record
        pending.delete()

        # Log the user in
        login(request, user, backend="accounts.backends.EmailBackend")

        logger.info("Registration complete — User created and logged in: %s", email)

        # Send WhatsApp welcome (non-blocking)
        if user.phone:
            async_task(
                "core.tasks.send_whatsapp_message",
                phone=user.phone,
                template_name="welcome_message",
                template_data={"name": user.full_name},
            )

        return Response(
            {
                "message": "Account created successfully. Welcome!",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# RESEND OTP
# =============================================================================

class ResendOTPView(APIView):
    """
    POST /accounts/resend-otp/

    Works for both PendingRegistration and unverified User accounts.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        generic_msg = "If a pending registration exists for this email, a new code has been sent."

        # Check PendingRegistration first
        pending_exists = PendingRegistration.objects.filter(email=email).exists()
        # Also check unverified User
        legacy_user_exists = User.objects.filter(email=email, is_active=False).exists()

        if not pending_exists and not legacy_user_exists:
            return Response({"message": generic_msg}, status=status.HTTP_200_OK)

        otp_code = create_and_store_otp(email)
        send_otp_email(email, otp_code)

        logger.info("OTP resent for: %s", email)
        return Response({"message": generic_msg}, status=status.HTTP_200_OK)


# =============================================================================
# LOGIN
# =============================================================================

class LoginView(APIView):
    """
    POST /accounts/login/

    Authenticate with email + password.
    - Checks account lockout
    - Prompts unverified accounts to verify
    - On success: creates Django session
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        if check_login_lock(email):
            return Response(
                {"error": "Account temporarily locked due to too many failed attempts. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        user = authenticate(request, email=email, password=password)

        if user is None:
            record_failed_login(email)
            return Response({"error": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_active:
            return Response(
                {
                    "error": "Your account has not been verified. Please check your email.",
                    "code": "ACCOUNT_NOT_VERIFIED",
                    "email": email,
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        reset_login_attempts(email)
        login(request, user, backend="accounts.backends.EmailBackend")
        logger.info("User logged in: %s", email)

        return Response(
            {"message": "Login successful.", "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


# =============================================================================
# LOGOUT & ME
# =============================================================================

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info("User logged out: %s", request.user.email)
        logout(request)
        return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"user": UserSerializer(request.user).data}, status=status.HTTP_200_OK)


# =============================================================================
# PAGE VIEWS
# =============================================================================

def login_page(request):
    return render(request, "accounts/login.html")


def register_page(request):
    return render(request, "accounts/register.html")


def employee_login_page(request):
    """
    Staff login page for employees.
    GET  — render the login form.
    POST — authenticate with email + password; on success redirect to /admin-portal/dashboard/.
    """
    from django.contrib.auth import authenticate as auth_authenticate, login as auth_login

    if request.user.is_authenticated and hasattr(request.user, 'userprofile'):
        if request.user.userprofile.role == 'employee':
            return redirect('/admin-portal/dashboard/')

    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        user = auth_authenticate(request, username=email, password=password)
        if user is not None and hasattr(user, 'userprofile') and user.userprofile.role == 'employee':
            auth_login(request, user, backend='accounts.backends.EmailBackend')
            return redirect('/admin-portal/dashboard/')
        else:
            error = 'Invalid credentials or insufficient permissions.'

    return render(request, 'accounts/employee_login.html', {'error': error})


def super_admin_login_page(request):
    """
    Super Admin login page.
    GET  — render the login form.
    POST — authenticate with email + password; on success redirect to /super-admin/dashboard/.
    """
    from django.contrib.auth import authenticate as auth_authenticate, login as auth_login

    if request.user.is_authenticated and hasattr(request.user, 'userprofile'):
        if request.user.userprofile.role == 'super_admin':
            return redirect('/super-admin/dashboard/')

    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        user = auth_authenticate(request, username=email, password=password)
        if user is not None and hasattr(user, 'userprofile') and user.userprofile.role == 'super_admin':
            auth_login(request, user, backend='accounts.backends.EmailBackend')
            return redirect('/super-admin/dashboard/')
        else:
            error = 'Invalid credentials or insufficient permissions.'

    return render(request, 'accounts/super_admin_login.html', {'error': error})


# =============================================================================
# FOLIO PAGE (Guest Dashboard)
# =============================================================================

from django.contrib.auth.decorators import login_required


@login_required(login_url='/accounts/login/page/')
def folio_page(request):
    from rooms.models import Booking
    bookings = Booking.objects.filter(user=request.user).select_related('room', 'room__property').order_by('-created_at')
    confirmed_bookings = bookings.filter(status='confirmed')
    total_spent = sum(b.total_price for b in bookings.filter(status__in=['confirmed', 'completed']))
    nights_stayed = sum(b.num_nights for b in bookings.filter(status__in=['confirmed', 'completed']))
    profile = getattr(request.user, 'userprofile', None)
    context = {
        'bookings': bookings[:10],
        'total_bookings': bookings.count(),
        'confirmed_count': confirmed_bookings.count(),
        'total_spent': total_spent,
        'nights_stayed': nights_stayed,
        'loyalty_points': getattr(profile, 'loyalty_points', 0),
        'loyalty_tier': getattr(profile, 'loyalty_tier', None),
    }
    return render(request, 'pages/folio.html', context)


@login_required(login_url='/accounts/login/page/')
def edit_profile_page(request):
    return render(request, 'accounts/edit_profile.html', {
        'back_url': '/accounts/folio/',
        'back_label': 'Back to folio',
    })


@login_required(login_url='/accounts/login/page/')
def update_profile(request):
    """AJAX endpoint: update name/phone immediately; email requires OTP."""
    import json
    import re
    if request.method != 'POST':
        from django.http import JsonResponse
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        from django.http import JsonResponse
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    from django.http import JsonResponse
    from django.core.cache import cache
    user = request.user
    field = data.get('field', '')

    if field == 'name':
        name = data.get('value', '').strip()
        if not name:
            return JsonResponse({'error': 'Name cannot be empty.'}, status=400)
        user.full_name = name
        user.save(update_fields=['full_name'])
        return JsonResponse({'message': 'Name updated successfully.'})

    if field == 'phone':
        phone = data.get('value', '').strip()
        if not re.match(r'^[6-9]\d{9}$', phone):
            return JsonResponse({'error': 'Enter a valid 10-digit Indian mobile number.'}, status=400)
        user.phone = phone
        user.save(update_fields=['phone'])
        return JsonResponse({'message': 'Phone updated successfully.'})

    if field == 'email_request':
        new_email = data.get('value', '').strip().lower()
        if not new_email or '@' not in new_email:
            return JsonResponse({'error': 'Enter a valid email address.'}, status=400)
        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            return JsonResponse({'error': 'That email is already in use.'}, status=400)
        otp_code = create_and_store_otp(new_email)
        send_otp_email(new_email, otp_code)
        cache.set(f'email_change:{user.pk}:{new_email}', True, timeout=600)
        return JsonResponse({'message': f'Verification code sent to {new_email}. Enter it below.'})

    if field == 'email_verify':
        new_email = data.get('email', '').strip().lower()
        otp = data.get('otp', '').strip()
        if not cache.get(f'email_change:{user.pk}:{new_email}'):
            return JsonResponse({'error': 'OTP expired or not initiated. Request a new one.'}, status=400)
        result = verify_otp(new_email, otp)
        if not result['success']:
            return JsonResponse({'error': result['error']}, status=400)
        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            return JsonResponse({'error': 'That email is already in use.'}, status=400)
        user.email = new_email
        user.save(update_fields=['email'])
        cache.delete(f'email_change:{user.pk}:{new_email}')
        return JsonResponse({'message': 'Email updated successfully.'})

    return JsonResponse({'error': 'Unknown field.'}, status=400)


# =============================================================================
# EMPLOYEE CREATION (Super Admin only)
# =============================================================================

class CreateEmployeeView(APIView):
    """POST /admin-api/employees/create/ — Super Admin only."""

    permission_classes = [IsSuperAdmin]

    def post(self, request):
        serializer = EmployeeCreationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        from .models import UserProfile
        from rooms.models import Property

        data = serializer.validated_data
        temp_password = secrets.token_urlsafe(12)

        user = User.objects.create_user(
            email=data["email"],
            full_name=data["full_name"],
            phone=data["phone"],
            password=temp_password,
        )
        user.is_active = True
        user.is_staff = data["role"] == "super_admin"
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = data["role"]
        profile.fin_level = data.get("fin_level")
        profile.must_change_password = True
        profile.save()

        if data.get("assigned_properties"):
            profile.assigned_properties.set(
                Property.objects.filter(id__in=data["assigned_properties"])
            )

        return Response(
            {
                "message": "Employee created successfully.",
                "email": user.email,
                "temporary_password": temp_password,
                "must_change_password": True,
            },
            status=status.HTTP_201_CREATED,
        )


# ── Forgot Password (3-step OTP reset) ────────────────────────────────────────

def forgot_password(request):
    """Step 1 — enter email, send OTP."""
    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if not email or '@' not in email:
            error = 'Please enter a valid email address.'
        else:
            user_exists = User.objects.filter(email=email, is_active=True).exists()
            if user_exists:
                otp_code = create_and_store_otp(email)
                send_otp_email(email, otp_code)
            # Always show success to avoid user enumeration
            request.session['pw_reset_email'] = email
            return redirect('accounts:forgot-password-verify')
    return render(request, 'accounts/forgot_password.html', {'error': error})


def forgot_password_verify(request):
    """Step 2 — enter OTP to verify identity."""
    email = request.session.get('pw_reset_email')
    if not email:
        return redirect('accounts:forgot-password')

    error = None
    if request.method == 'POST':
        code = request.POST.get('otp', '').strip()
        result = verify_otp(email, code)
        if result['success']:
            request.session['pw_reset_verified'] = True
            return redirect('accounts:forgot-password-set')
        error = result['error']

    return render(request, 'accounts/forgot_password_verify.html', {'email': email, 'error': error})


def forgot_password_set(request):
    """Step 3 — set new password."""
    email = request.session.get('pw_reset_email')
    verified = request.session.get('pw_reset_verified')
    if not email or not verified:
        return redirect('accounts:forgot-password')

    error = None
    if request.method == 'POST':
        pw1 = request.POST.get('password1', '')
        pw2 = request.POST.get('password2', '')
        if len(pw1) < 8:
            error = 'Password must be at least 8 characters.'
        elif pw1 != pw2:
            error = 'Passwords do not match.'
        else:
            try:
                user = User.objects.get(email=email, is_active=True)
                user.set_password(pw1)
                user.save()
                # Clear session keys
                request.session.pop('pw_reset_email', None)
                request.session.pop('pw_reset_verified', None)
                return redirect('accounts:login-page')
            except User.DoesNotExist:
                error = 'Account not found.'

    return render(request, 'accounts/forgot_password_set.html', {'error': error})
