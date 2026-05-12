"""
WSGI config for hotel_booking project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hotel_booking.settings.dev")
application = get_wsgi_application()
