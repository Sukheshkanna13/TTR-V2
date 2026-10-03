from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from core.middleware import ProxyRemoteAddrMiddleware


class ProxyRemoteAddrMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.seen = {}

        def view(request):
            self.seen["addr"] = request.META.get("REMOTE_ADDR")
            return HttpResponse("ok")

        self.middleware = ProxyRemoteAddrMiddleware(view)
        self.factory = RequestFactory()

    def test_uses_last_forwarded_hop(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="203.0.113.7", REMOTE_ADDR="127.0.0.1")
        self.middleware(request)
        self.assertEqual(self.seen["addr"], "203.0.113.7")

    def test_spoofed_leading_entries_are_ignored(self):
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7", REMOTE_ADDR="127.0.0.1"
        )
        self.middleware(request)
        self.assertEqual(self.seen["addr"], "203.0.113.7")

    def test_invalid_value_keeps_original_address(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="not-an-ip", REMOTE_ADDR="127.0.0.1")
        self.middleware(request)
        self.assertEqual(self.seen["addr"], "127.0.0.1")

    def test_missing_header_keeps_original_address(self):
        request = self.factory.get("/", REMOTE_ADDR="127.0.0.1")
        self.middleware(request)
        self.assertEqual(self.seen["addr"], "127.0.0.1")
