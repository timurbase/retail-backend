"""
Active store / audit context middleware.

Note: DRF's JWTAuthentication runs inside the view dispatch (not in
classic Django middleware), so request.auth isn't populated yet when
this middleware fires. We just install a lazy attribute here; the real
resolution happens inside the HasActiveStore permission, which runs
after authentication.
"""

from __future__ import annotations


class ActiveStoreMiddleware:
    """Initialises request attributes; permission classes do the work."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_store_id = None
        return self.get_response(request)
