"""
Middleware for running behind a reverse proxy (nginx on the VPS).
"""

import ipaddress


class ProxyRemoteAddrMiddleware:
    """
    Behind nginx every request reaches gunicorn from 127.0.0.1 (or a unix
    socket), which would put all guests in one DRF throttle bucket and stamp
    a wrong IP on audit-log rows.

    nginx overwrites X-Forwarded-For with the real client address
    (``proxy_set_header X-Forwarded-For $remote_addr``), so the last hop is
    trustworthy. Enable only in production, and only when nginx (or another
    proxy that overwrites the header) is the sole way to reach gunicorn.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        client = forwarded.split(",")[-1].strip()
        if client:
            try:
                ipaddress.ip_address(client)
            except ValueError:
                pass
            else:
                request.META["REMOTE_ADDR"] = client
        return self.get_response(request)
