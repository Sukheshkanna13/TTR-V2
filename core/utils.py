from django.conf import settings
from django.templatetags.static import static


def email_logo_url():
    """Absolute URL of the brand logo for HTML emails, or "" if SITE_URL is unset."""
    if not settings.SITE_URL:
        return ""
    return f"{settings.SITE_URL}{static('images/TTR-Logo.png')}"
