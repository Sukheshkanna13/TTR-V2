"""
Django settings for hotel_booking project.
Phase 1: Authentication System (Simplified Architecture)

Pipeline: Browser -> Django -> SQLite -> Gmail SMTP -> Razorpay
"""

import os
from pathlib import Path

from decouple import Csv, config

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# =============================================================================
# CORE SETTINGS
# =============================================================================

SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me-in-production")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())


# =============================================================================
# INSTALLED APPS
# =============================================================================

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    # Local apps
    "accounts",
    "rooms",
    "payments",
]


# =============================================================================
# DJANGO-UNFOLD ADMIN THEME
# =============================================================================

UNFOLD = {
    "SITE_TITLE": "Hotel Booking Admin",
    "SITE_HEADER": "Hotel Booking",
    "SITE_SUBHEADER": "Management Dashboard",
    "DASHBOARD_CALLBACK": "hotel_booking.dashboard.dashboard_callback",
    "SIDEBAR": {
        "navigation": [
            {
                "title": "Dashboard",
                "items": [
                    {
                        "title": "Home",
                        "icon": "home",
                        "link": "/admin/",
                    },
                ],
            },
            {
                "title": "Bookings & Payments",
                "items": [
                    {
                        "title": "Bookings",
                        "icon": "book_online",
                        "link": "/admin/rooms/booking/",
                    },
                    {
                        "title": "Payments",
                        "icon": "payments",
                        "link": "/admin/payments/payment/",
                    },
                ],
            },
            {
                "title": "Hotel",
                "items": [
                    {
                        "title": "Rooms",
                        "icon": "hotel",
                        "link": "/admin/rooms/room/",
                    },
                ],
            },
            {
                "title": "Users & Auth",
                "items": [
                    {
                        "title": "Users",
                        "icon": "people",
                        "link": "/admin/accounts/user/",
                    },
                    {
                        "title": "OTP Codes",
                        "icon": "pin",
                        "link": "/admin/accounts/otp/",
                    },
                    {
                        "title": "Login Attempts",
                        "icon": "security",
                        "link": "/admin/accounts/loginattempt/",
                    },
                ],
            },
        ],
    },
}


# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "hotel_booking.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "hotel_booking.wsgi.application"


# =============================================================================
# DATABASE — SQLite (Django's built-in, no setup needed)
# =============================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# =============================================================================
# CUSTOM USER MODEL
# =============================================================================

AUTH_USER_MODEL = "accounts.User"


# =============================================================================
# AUTHENTICATION BACKENDS
# =============================================================================

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",
]


# =============================================================================
# PASSWORD HASHERS — bcrypt first
# =============================================================================

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]


# =============================================================================
# PASSWORD VALIDATION
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# =============================================================================
# SESSION — Database backed (default Django behavior)
# =============================================================================

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 86400  # 24 hours in seconds
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = True


# =============================================================================
# EMAIL — Gmail SMTP
# =============================================================================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="").replace(" ", "")
DEFAULT_FROM_EMAIL = config("EMAIL_HOST_USER", default="noreply@hotelbooking.com")


# =============================================================================
# DJANGO REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.backends.CsrfExemptSessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
}


# =============================================================================
# CORS (for frontend)
# =============================================================================

CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only in development
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000,http://127.0.0.1:8080,http://localhost:8080",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True


# =============================================================================
# OTP CONFIGURATION
# =============================================================================

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 3

# Login rate limiting
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_DURATION_MINUTES = 15


# =============================================================================
# RAZORPAY CONFIGURATION
# =============================================================================

RAZORPAY_KEY_ID = config("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = config("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = config("RAZORPAY_WEBHOOK_SECRET", default="")


# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# =============================================================================
# STATIC FILES
# =============================================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# =============================================================================
# DEFAULT PRIMARY KEY FIELD TYPE
# =============================================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
