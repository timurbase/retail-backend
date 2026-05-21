"""
record(...) — the single entry point every mutation must call.

We keep it module-level (not on the model) so callers can't accidentally
construct a partial AuditEntry. Snapshots actor data so the log survives
user deletion.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from .models import AuditEntry


def _client_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record(
    request: HttpRequest | None = None,
    *,
    actor=None,
    store_id=None,
    action: str,
    object_type: str,
    object_id: str,
    object_label: str = "",
    details: str = "",
    extra: dict[str, Any] | None = None,
) -> AuditEntry:
    """Write a single audit row. Pull actor/store from request if not given."""

    if actor is None and request is not None:
        actor = getattr(request, "user", None)
        if actor is not None and not getattr(actor, "is_authenticated", False):
            actor = None

    if store_id is None and request is not None:
        store_id = getattr(request, "active_store_id", None)

    actor_snapshot: dict[str, Any] = {}
    actor_fk = None
    if actor is not None:
        actor_fk = actor
        # Try to read role via active membership for the snapshot
        role = None
        if store_id is not None:
            try:
                from apps.accounts.models import Membership

                role = (
                    Membership.objects.filter(user=actor, store_id=store_id)
                    .values_list("role", flat=True)
                    .first()
                )
            except Exception:
                role = None
        actor_snapshot = {
            "id": str(actor.id),
            "name": getattr(actor, "full_name", "") or actor.phone,
            "role": role,
        }
    if extra:
        actor_snapshot["extra"] = extra

    return AuditEntry.objects.create(
        store_id=store_id,
        actor=actor_fk,
        actor_snapshot=actor_snapshot,
        action=action,
        object_type=object_type,
        object_id=object_id,
        object_label=object_label[:300],
        details=details,
        ip=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:500] if request else ""),
    )
