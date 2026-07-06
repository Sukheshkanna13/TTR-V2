"""
Production settings for hotel_booking project.
Deployed on Render (free tier — PostgreSQL, no Redis).
"""
from .base import *
import dj_database_url

DEBUG = False

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

# Database — Render auto-injects DATABASE_URL for the linked PostgreSQL
DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

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
# EMAIL — Console Backend (Render Free Tier blocks outbound SMTP ports)
# =============================================================================
# We must use the console backend on Render's free tier to avoid timeouts.
# The OTP will be printed to your Render Logs tab instead of sending a real email.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

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
