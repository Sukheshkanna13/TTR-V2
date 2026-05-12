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
