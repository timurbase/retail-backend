"""
Supplier (yetkazib beruvchi) catalog — store-side directory.

Mirrors lib/types.ts → Supplier on the frontend. Multi-tenancy ready
via TenantScoped (store_id required, org_id NULL today).
"""

from django.db import models

from apps.core.models import TenantScoped


class Supplier(TenantScoped):
    name = models.CharField(max_length=200)
    stir = models.CharField(max_length=14)
    verified = models.BooleanField(default=False)
    soliq_last_checked = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "suppliers_supplier"
        unique_together = (("store", "stir"),)
        indexes = [
            models.Index(fields=("store", "name")),
            models.Index(fields=("store", "verified")),
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.stir})"
