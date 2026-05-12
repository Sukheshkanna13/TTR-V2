"""
API views for the accounts app.

Simplified architecture: Browser → Django → PostgreSQL → Gmail SMTP
Authentication: Django sessions (cookie-based)

Endpoints:
    POST /accounts/register/     — Register a new user
    POST /accounts/verify-otp/   — Verify OTP and activate account
    POST /accounts/resend-otp/   — Resend OTP email
    POST /accounts/login/        — Login with email & password
    POST /accounts/logout/       — Logout (clear session)
"""

import logging

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.shortcuts import render
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_q.tasks import async_task

from .permissions import IsSuperAdmin

from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    ResendOTPSerializer,
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


class RegisterView(APIView):
    """
    POST /accounts/register/

    Register a new user account.
    1. Validates input (duplicates, phone format, password strength)
    2. Creates user with is_active=False and bcrypt-hashed password
    3. Generates 6-digit OTP and stores in PostgreSQL (10-min expiry)
    4. Sends OTP email directly via Gmail SMTP
    5. Returns 201
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save user (is_active=False, password hashed with bcrypt)
        user = serializer.save()

        # Generate OTP and store in database
        otp_code = create_and_store_otp(user.email)

        # Send OTP email directly (no background task)
        email_sent = send_otp_email(user.email, otp_code)

        logger.info("User registered: %s — OTP email sent: %s", user.email, email_sent)

        return Response(
            {
                "message": "Registration successful. Please check your email for the verification code.",
                "email": user.email,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyOTPView(APIView):
    """
    POST /accounts/verify-otp/

    Verify the OTP sent to the user's email.
    - Max 3 attempts before blocking
    - On success: activate user, delete OTP, log in with Django session
    - On expired OTP: prompt to resend
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]
        submitted_otp = serializer.validated_data["otp"]

        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "No account found with this email."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if already verified
        if user.is_active:
            return Response(
                {"error": "This account is already verified. Please log in."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify the OTP against the database
        result = verify_otp(email, submitted_otp)

        if not result["success"]:
            # Determine the appropriate HTTP status
            code = result["code"]
            if code == "OTP_BLOCKED":
                http_status = status.HTTP_429_TOO_MANY_REQUESTS
            elif code == "OTP_EXPIRED":
                http_status = status.HTTP_410_GONE
            else:
                http_status = status.HTTP_400_BAD_REQUEST

            return Response(
                {"error": result["error"], "code": code},
                status=http_status,
            )

        # OTP verified — activate user
        user.is_active = True
        user.save(update_fields=["is_active"])

        # Auto-login: create Django session
        login(request, user, backend="accounts.backends.EmailBackend")

        logger.info("User verified and activated: %s", email)

        if user.phone:
            async_task(
                'core.tasks.send_whatsapp_message',
                phone=user.phone,
                template_name='welcome_message',
                template_data={
                    "name": user.full_name
                }
            )

        return Response(
            {
                "message": "Email verified successfully. You are now logged in.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class ResendOTPView(APIView):
    """
    POST /accounts/resend-otp/

    Resend OTP to user's email.
    - Only works for existing, unverified users
    - Generates a fresh OTP and resets attempt counters
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data["email"]

        # Generic response message (don't reveal account existence)
        generic_msg = "If an account exists with this email, a new verification code has been sent."

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"message": generic_msg},
                status=status.HTTP_200_OK,
            )

        if user.is_active:
            return Response(
                {"message": generic_msg},
                status=status.HTTP_200_OK,
            )

        # Generate new OTP and send email
        otp_code = create_and_store_otp(email)
        send_otp_email(email, otp_code)

        logger.info("OTP resent for: %s", email)

        return Response(
            {"message": generic_msg},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    """
    POST /accounts/login/

    Authenticate user with email and password.
    - Checks for account lockout (5 failed attempts → 15-min lock)
    - Unverified accounts prompted to verify
    - Generic error messages (never reveals which field is wrong)
    - On success: creates Django session, sets cookie
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)

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
            # Authentication failed — record the attempt
            record_failed_login(email)
            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
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

        # Successful login — reset attempt counters
        reset_login_attempts(email)

        # Create Django session and set cookie
        login(request, user, backend="accounts.backends.EmailBackend")

        logger.info("User logged in: %s", email)

        return Response(
            {
                "message": "Login successful.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """
    POST /accounts/logout/

    Logout the current user.
    - Clears the Django session
    - Removes the session cookie
    - Redirects to login page (handled by frontend)
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info("User logged out: %s", request.user.email)

        # Clear the Django session entirely
        logout(request)

        return Response(
            {"message": "Logged out successfully."},
            status=status.HTTP_200_OK,
        )

class CurrentUserView(APIView):
    """
    GET /accounts/me/
    
    Returns the currently logged-in user's profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {"user": UserSerializer(request.user).data},
            status=status.HTTP_200_OK
        )


# ============================================================================
# PAGE VIEWS (Template Rendering)
# ============================================================================

def login_page(request):
    """Render the user login page template."""
    return render(request, "accounts/login.html")


def register_page(request):
    """Render the user registration page template."""
    return render(request, "accounts/register.html")


class CreateEmployeeView(APIView):
    """
    POST /admin-api/employees/create/
    
    Super Admin only endpoint to create employee accounts.
    """
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        serializer = EmployeeCreationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        import secrets
        from .models import UserProfile
        from rooms.models import Property

        data = serializer.validated_data
        
        # Create user with a random temporary password
        temp_password = secrets.token_urlsafe(12)
        user = User.objects.create_user(
            email=data['email'],
            full_name=data['full_name'],
            phone=data['phone'],
            password=temp_password,
        )
        user.is_active = True
        user.is_staff = True if data['role'] == 'super_admin' else False
        user.save()

        # Create user profile
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.role = data['role']
        profile.fin_level = data.get('fin_level')
        profile.must_change_password = True
        profile.save()

        # Assign properties if provided
        assigned_properties = data.get('assigned_properties', [])
        if assigned_properties:
            properties = Property.objects.filter(id__in=assigned_properties)
            profile.assigned_properties.set(properties)

        return Response({
            "message": "Employee created successfully.",
            "email": user.email,
            "temporary_password": temp_password,
            "must_change_password": True
        }, status=status.HTTP_201_CREATED)
