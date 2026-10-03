"""
Production settings for hotel_booking project.

Runs on either target, selected purely through environment variables:
  - Render free tier (default): PostgreSQL, console email, no proxy trust.
  - Ubuntu VPS behind nginx: MySQL/PostgreSQL via DATABASE_URL, SMTP via
    EMAIL_BACKEND, TRUST_PROXY_HEADERS=True. See docs/VPS-DEPLOYMENT.md.
"""
from .base import *  # NOSONAR
import dj_database_url

DEBUG = config("DEBUG", default=False, cast=bool)

# Production security assertion guards
if not config("DATABASE_URL", default=None):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("DATABASE_URL environment variable must be set in production.")

if SECRET_KEY == "django-insecure-hotel-booking-dev-key-change-in-production":
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("SECRET_KEY must be configured with a secure production secret.")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default=".onrender.com", cast=Csv())

# Trust Render's proxy and its *.onrender.com domain for CSRF
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="https://*.onrender.com",
    cast=Csv(),
)

# Whitenoise for static files (serves CSS/JS/images directly from the app)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
# Security Headers
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Database — DATABASE_URL is required (guarded above). Render injects a
# PostgreSQL URL; on a VPS use e.g. mysql://user:pass@127.0.0.1:3306/ttr_v2
DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=600,
        conn_health_checks=True,
    )
}
if DATABASES["default"]["ENGINE"].endswith("mysql"):
    # Full unicode (guest names, emoji in reviews) and strict SQL mode so bad
    # data raises instead of being silently truncated.
    DATABASES["default"].setdefault("OPTIONS", {}).update(
        {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    )

# Reverse proxy (nginx on a VPS). nginx must overwrite X-Forwarded-For with the
# real client address; without this every guest shares one throttle bucket and
# audit-log rows record 127.0.0.1. Leave False when gunicorn is directly exposed.
TRUST_PROXY_HEADERS = config("TRUST_PROXY_HEADERS", default=False, cast=bool)
if TRUST_PROXY_HEADERS:
    MIDDLEWARE.insert(0, "core.middleware.ProxyRemoteAddrMiddleware")
    REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": 0}  # ident = REMOTE_ADDR

# Logging — console only (Render filesystem is ephemeral, no file logging)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": config("DJANGO_LOG_LEVEL", default="INFO"),
        },
        "accounts": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "rooms": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "payments": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}

# =============================================================================
# EMAIL
# =============================================================================
# Default is the console backend because Render's free tier blocks outbound SMTP.
# OTPs are then PRINTED TO THE LOGS and no guest receives an email, so on a VPS
# set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend in the env file.
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

# Inherits Gmail SMTP from base.py. Override with SendGrid when you have a key:
# EMAIL_HOST = "smtp.sendgrid.net"
# EMAIL_HOST_USER = "apikey"
# EMAIL_HOST_PASSWORD = config("SENDGRID_API_KEY", default="")
# DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@templetowns.com")

# =============================================================================
# DJANGO Q (Task Queue) — ORM broker (no Redis on free tier)
# =============================================================================
Q_CLUSTER = {
    "name": "ttr_prod",
    "orm": "default",        # Uses the PostgreSQL database as the broker
    "timeout": 60,
    "retry": 120,
    "save_limit": 250,
    "queue_limit": 500,
    "cpu_affinity": 1,
    "label": "Django Q",
}
