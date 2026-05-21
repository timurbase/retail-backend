"""
AuditContextMiddleware — placeholder so views can rely on request having
the audit shape. Currently no-op; will hold request-scoped session ID and
correlation ID once we wire structured logging.
"""

from __future__ import annotations


class AuditContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.audit_correlation_id = None  # reserved
        return self.get_response(request)
