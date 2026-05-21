"""
Core abstract models — every domain model in RetailFlow inherits one of these.

TimeStamped       — created_at / updated_at audit columns.
TenantScoped      — adds store_id (required) and org_id (NULL OK).
                    CLAUDE.md rule: multi-tenancy must be ready from day one.
"""

import uuid

from django.db import models


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantScoped(TimeStamped):
    """All tenant-bound data carries a store_id; org_id is reserved for the
    distributor rollout (deferred, NULL today)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        "tenants.Store",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
    )
    org = models.ForeignKey(
        "tenants.Org",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True
