"""
Product catalog + stock movements.

Mirrors lib/types.ts → Product. StockMovement is the immutable
audit trail of every quantity change (kirim/chiqim/inventarizatsiya/
doc_approve) — recorded atomically with the parent transaction.
"""


from django.db import models

from apps.core.models import TenantScoped


class Product(TenantScoped):
    name = models.CharField(max_length=200)
    # FK to MxikCode comes later — keep as plain code for now
    mxik = models.CharField(max_length=10, blank=True, db_index=True)
    unit = models.CharField(max_length=20)
    current_stock = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    min_stock = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    avg_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    last_received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "products_product"
        indexes = [
            models.Index(fields=("store", "name")),
            models.Index(fields=("store", "mxik")),
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class StockMovementKind(models.TextChoices):
    KIRIM = "kirim", "Kirim"
    CHIQIM = "chiqim", "Chiqim"
    INVENTARIZATSIYA = "inventarizatsiya", "Inventarizatsiya"
    DOC_APPROVE = "doc_approve", "Hujjat tasdiqi"


class StockMovement(TenantScoped):
    """Append-only stock-change log. Sign of `delta` follows kind:
    kirim (+), chiqim (−), inventarizatsiya (+/− to reach exact),
    doc_approve (+). before/after captures the value snapshot."""

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="movements"
    )
    kind = models.CharField(max_length=20, choices=StockMovementKind.choices)
    delta = models.DecimalField(max_digits=14, decimal_places=3)
    before = models.DecimalField(max_digits=14, decimal_places=3)
    after = models.DecimalField(max_digits=14, decimal_places=3)
    reason = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # No FK yet — documents app stamps this after the row resolves
    document_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "products_stock_movement"
        indexes = [
            models.Index(fields=("product", "-created_at")),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.product_id} {self.kind} {self.delta}"
