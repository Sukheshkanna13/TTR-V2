"""
Development settings for hotel_booking project.
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# Disable password validators in dev for easier testing if desired, or keep them.
# Email backend is already configured for Gmail SMTP in base.py (used as dev).

# CORS allowing all in dev
CORS_ALLOW_ALL_ORIGINS = True

# Development login testing should not trap admins for long while flows are being tested.
LOGIN_MAX_ATTEMPTS = 20
LOGIN_LOCK_DURATION_MINUTES = 1
