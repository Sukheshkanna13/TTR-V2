from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings

from core.utils import email_logo_url


class EmailLogoTests(SimpleTestCase):
    @override_settings(SITE_URL="https://ttr.example")
    def test_logo_url_is_absolute(self):
        self.assertEqual(email_logo_url(), "https://ttr.example/static/images/TTR-Logo.png")

    @override_settings(SITE_URL="")
    def test_logo_url_empty_without_site_url(self):
        self.assertEqual(email_logo_url(), "")

    def test_otp_email_renders_logo_only_when_given(self):
        with_logo = render_to_string("emails/otp_email.html", {"otp": "123456", "year": 2026, "logo_url": "https://x/l.png"})
        without = render_to_string("emails/otp_email.html", {"otp": "123456", "year": 2026, "logo_url": ""})
        self.assertIn('src="https://x/l.png"', with_logo)
        self.assertNotIn("<img", without)
