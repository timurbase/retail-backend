"""
Retail documents — kelib tushgan tovar hujjatlari.

Mirrors lib/types.ts → RetailDocument + ProductRow. Each document has
N rows; rows are matched against products.Product via MXIK + name.
"""

import uuid

from django.db import models

from apps.core.models import TenantScoped


class DocumentSource(models.TextChoices):
    DIDOX = "didox", "Didox"
    EXCEL = "excel", "Excel"
    PDF = "pdf", "PDF"
    PHOTO = "photo", "Foto"
    MANUAL = "manual", "Qo'lda"


class DocumentStatus(models.TextChoices):
    PENDING = "pending", "Tahlil qilinmoqda"
    REVIEW = "review", "Ko'rib chiqilmoqda"
    APPROVED = "approved", "Tasdiqlangan"
    REJECTED = "rejected", "Rad etilgan"
    DUPLICATE = "duplicate", "Dublikat"


class ProductRowStatus(models.TextChoices):
    MATCHED = "matched", "Mos kelgan"
    NEW = "new", "Yangi"
    AMBIGUOUS = "ambiguous", "Noaniq"
    APPROVED = "approved", "Tasdiqlangan"
    REJECTED = "rejected", "Rad etilgan"


class RetailDocument(TenantScoped):
    number = models.CharField(max_length=50)
    source = models.CharField(max_length=10, choices=DocumentSource.choices)
    supplier = models.ForeignKey(
        "suppliers.Supplier",
        on_delete=models.PROTECT,
        related_name="documents",
    )
    date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.PENDING,
    )
    review_count = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    dedup_hash = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        db_table = "documents_retail_document"
        indexes = [
            models.Index(fields=("store", "-created_at")),
            models.Index(fields=("store", "status")),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"Hujjat №{self.number}"


class ProductRow(models.Model):
    """Document line. Plain model (not TenantScoped) because store_id is
    inherited via document.store — no need to denormalize."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        RetailDocument, on_delete=models.CASCADE, related_name="rows"
    )
    raw_name = models.CharField(max_length=500)
    mapped_product = models.ForeignKey(
        "products.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rows",
    )
    mxik_code = models.CharField(max_length=10, blank=True)
    mxik_name = models.CharField(max_length=500, blank=True)
    mxik_confidence = models.FloatField(default=0)
    alternatives = models.JSONField(default=list, blank=True)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=ProductRowStatus.choices,
        default=ProductRowStatus.NEW,
    )
    order_index = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "documents_product_row"
        indexes = [
            models.Index(fields=("document", "order_index")),
            models.Index(fields=("status",)),
        ]
        ordering = ("order_index", "created_at")

    def __str__(self) -> str:
        return f"{self.raw_name} ({self.status})"
