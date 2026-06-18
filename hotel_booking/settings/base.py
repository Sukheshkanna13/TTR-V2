"""
Django settings for hotel_booking project.
Base settings common to all environments.
"""

import os
from pathlib import Path
from decouple import Csv, config
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# Now that settings is a package (hotel_booking/settings/base.py),
# BASE_DIR should point to the repository root.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third-party
    "rest_framework",
    "corsheaders",
    "django_q",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    # Local apps
    "core",
    "accounts",
    "rooms",
    "payments",
    "superadmin",
    "employeeadmin",
    "loyalty",
]

SITE_ID = 1



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
    "accounts.middleware.RoleRoutingMiddleware",
    "accounts.middleware.AutoLogoutMiddleware",
    "accounts.middleware.ForcePasswordChangeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
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
                "loyalty.context_processors.loyalty_context",
            ],
        },
    },
]

WSGI_APPLICATION = "hotel_booking.wsgi.application"


# =============================================================================
# DATABASE
# =============================================================================

# Default to SQLite but allow override via DATABASE_URL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'ttr_v2',
        'USER': 'root',
        'PASSWORD': 'vengeance',
        'HOST': '127.0.0.1',
        'PORT': '3306',
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
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
    "accounts.backends.EmailBackend",
]

# Allauth Settings
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
# allauth ≥65 API
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"  # OTP handled separately

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    }
}

SOCIALACCOUNT_ADAPTER = 'accounts.adapter.CustomSocialAccountAdapter'

# =============================================================================
# PASSWORD HASHERS
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
# SESSION
# =============================================================================

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 86400  # 24 hours in seconds
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = True


# =============================================================================
# EMAIL (Base - Overridden in dev/prod)
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
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
}


# =============================================================================
# CORS
# =============================================================================

CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=DEBUG, cast=bool)
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000,http://127.0.0.1:8080,http://localhost:8080",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True


# =============================================================================
# OTP AND BOOKING CONFIGURATION
# =============================================================================

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 3

# Login rate limiting
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCK_DURATION_MINUTES = 15

# Booking hold duration
HOLD_DURATION_MINUTES = config("HOLD_DURATION_MINUTES", default=10, cast=int)


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
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# =============================================================================
# STATIC FILES
# =============================================================================

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


# =============================================================================
# MEDIA FILES
# =============================================================================

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# =============================================================================
# DEFAULT PRIMARY KEY FIELD TYPE
# =============================================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =============================================================================
# DJANGO Q (Task Queue)
# =============================================================================

Q_CLUSTER = {
    "name": "ttr",
    "orm": "default",  # Use Django ORM as broker
    "timeout": 60,
    "retry": 120,
    "save_limit": 250,
    "queue_limit": 500,
    "cpu_affinity": 1,
    "label": "Django Q",
}
