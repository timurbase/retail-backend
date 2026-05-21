"""
Audit log — append-only.

CLAUDE.md rule: "Audit log immutability — append-only, PostgreSQL trigger."
We declare the model with no UPDATE/DELETE manager methods, and a data
migration installs a row-level trigger that blocks mutations at the DB
level so even direct SQL can't tamper with history.
"""

import uuid

from django.db import models


class AuditAction(models.TextChoices):
    CREATE = "create", "Create"
    UPDATE = "update", "Update"
    DELETE = "delete", "Delete"
    APPROVE = "approve", "Approve"
    REJECT = "reject", "Reject"
    AUTH = "auth", "Auth"
    VIEW = "view", "View"
    SYSTEM = "system", "System"


class AppendOnlyManager(models.Manager):
    def delete(self):
        raise NotImplementedError("Audit entries are immutable")


class AuditEntry(models.Model):
    """Single immutable event. object_type/object_id is a soft FK — we
    don't enforce referential integrity because targets may be deleted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    store = models.ForeignKey(
        "tenants.Store",
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_entries",
    )

    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    # Snapshot at write time so deleted users still show up in the log
    actor_snapshot = models.JSONField(default=dict)

    action = models.CharField(max_length=20, choices=AuditAction.choices)
    object_type = models.CharField(max_length=30)
    object_id = models.CharField(max_length=64)
    object_label = models.CharField(max_length=300, blank=True)
    details = models.TextField(blank=True)

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    objects = AppendOnlyManager()

    class Meta:
        db_table = "audit_entry"
        indexes = [
            models.Index(fields=("store", "-timestamp")),
            models.Index(fields=("object_type", "object_id")),
            models.Index(fields=("actor", "-timestamp")),
        ]
        ordering = ("-timestamp",)

    def __str__(self) -> str:
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.action} {self.object_type} {self.object_label}"

    def save(self, *args, **kwargs):
        if self.pk and AuditEntry.objects.filter(pk=self.pk).exists():
            raise ValueError("Audit entries are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError("Audit entries are immutable")
