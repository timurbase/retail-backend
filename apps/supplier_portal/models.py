"""
Supplier portal models — the distribyutor side of the platform.

SupplierCompany is the tenant; everything else carries a `supplier` FK to it.
Mirrors lib/types.ts → Supplier* on the frontend.

Multi-tenancy: each SupplierCompany is an independent tenant. Membership
rows in `apps.accounts.Membership` with portal="supplier" + tenant_id=<id>
gate access via the HasActiveSupplier permission.
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.core.models import TimeStamped


class BrandType(models.TextChoices):
    LOCAL = "local", "Mahalliy"
    INTERNATIONAL = "international", "Xalqaro"
    EXCLUSIVE = "exclusive", "Eksklyuziv"


class SupplierStoreStatus(models.TextChoices):
    ACTIVE = "active", "Faol"
    SLOW = "slow", "Sekin"
    INACTIVE = "inactive", "Nofaol"


class SupplierProductCategory(models.TextChoices):
    ICHIMLIKLAR = "ichimliklar", "Ichimliklar"
    OZIQ_OVQAT = "oziq-ovqat", "Oziq-ovqat"
    SIGARET = "sigaret", "Sigaret"
    MAISHIY = "maishiy", "Maishiy"
    KOSMETIKA = "kosmetika", "Kosmetika"
    BOSHQA = "boshqa", "Boshqa"


class OutgoingInvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Qoralama"
    SENT = "sent", "Yuborilgan"
    RECEIVED = "received", "Qabul qilingan"
    APPROVED = "approved", "Tasdiqlangan"
    PREPARING = "preparing", "Tayyorlanmoqda"
    DELIVERING = "delivering", "Yetkazilmoqda"
    DELIVERED = "delivered", "Yetkazildi"
    PAID = "paid", "To'landi"
    CANCELLED = "cancelled", "Bekor qilindi"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Kutilmoqda"
    PAID = "paid", "To'langan"
    OVERDUE = "overdue", "Muddati o'tgan"
    PARTIAL = "partial", "Qisman"


class PaymentMethod(models.TextChoices):
    CLICK = "click", "Click"
    PAYME = "payme", "Payme"
    BANK = "bank", "Bank"
    CASH = "cash", "Naqd"


class DemandHotness(models.TextChoices):
    RISING = "rising", "O'sayotgan"
    STABLE = "stable", "Barqaror"
    FALLING = "falling", "Pasayayotgan"


class IncomingOrderStatus(models.TextChoices):
    PENDING = "pending", "Kutilmoqda"
    ACCEPTED = "accepted", "Qabul qilindi"
    REJECTED = "rejected", "Rad etildi"
    FULFILLED = "fulfilled", "Bajarildi"


class DeliveryStopStatus(models.TextChoices):
    PENDING = "pending", "Kutilmoqda"
    DELIVERED = "delivered", "Yetkazildi"


class SupplierCompany(TimeStamped):
    """Distribyutor tenant root."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    stir = models.CharField(max_length=14, unique=True)
    director = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    brand_type = models.CharField(
        max_length=20, choices=BrandType.choices, default=BrandType.LOCAL
    )
    region = models.CharField(max_length=100)
    fleet_size = models.PositiveIntegerField(default=0)
    warehouse_address = models.TextField(blank=True)

    class Meta:
        db_table = "supplier_portal_company"
        verbose_name_plural = "Supplier companies"

    def __str__(self) -> str:
        return f"{self.name} ({self.stir})"


class SupplierStore(TimeStamped):
    """Customer store the supplier serves."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        SupplierCompany,
        on_delete=models.CASCADE,
        related_name="customer_stores",
        db_index=True,
    )
    # Soft FK to tenants.Store — nullable for legacy/unregistered customers
    store_id = models.UUIDField(null=True, blank=True, db_index=True)

    name = models.CharField(max_length=200)
    stir = models.CharField(max_length=14)
    director = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=20,
        choices=SupplierStoreStatus.choices,
        default=SupplierStoreStatus.ACTIVE,
    )
    reliability_score = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    monthly_volume = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_lifetime_volume = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    last_order_at = models.DateTimeField(null=True, blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    outstanding_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    growth_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = "supplier_portal_store"
        unique_together = (("supplier", "stir"),)
        indexes = [
            models.Index(fields=("supplier", "status")),
            models.Index(fields=("supplier", "-last_order_at")),
            models.Index(fields=("supplier", "-monthly_volume")),
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.stir})"


class SupplierProduct(TimeStamped):
    """Supplier's catalog item."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        SupplierCompany,
        on_delete=models.CASCADE,
        related_name="products",
        db_index=True,
    )
    name = models.CharField(max_length=200)
    mxik = models.CharField(max_length=10, blank=True)
    category = models.CharField(
        max_length=20,
        choices=SupplierProductCategory.choices,
        default=SupplierProductCategory.BOSHQA,
    )
    unit = models.CharField(max_length=20)
    base_price = models.DecimalField(max_digits=14, decimal_places=2)
    stock = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    monthly_sales = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    trend_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = "supplier_portal_product"
        indexes = [
            models.Index(fields=("supplier", "category")),
            models.Index(fields=("supplier", "name")),
        ]
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class OutgoingInvoice(TimeStamped):
    """Supplier → store invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        SupplierCompany,
        on_delete=models.CASCADE,
        related_name="outgoing_invoices",
        db_index=True,
    )
    store = models.ForeignKey(
        SupplierStore,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    number = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20,
        choices=OutgoingInvoiceStatus.choices,
        default=OutgoingInvoiceStatus.DRAFT,
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tracking_note = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "supplier_portal_invoice"
        indexes = [
            models.Index(fields=("supplier", "-created_at")),
            models.Index(fields=("status", "supplier")),
        ]
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.number


class OutgoingInvoiceItem(TimeStamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        OutgoingInvoice, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        SupplierProduct, on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField(max_length=200)
    mxik = models.CharField(max_length=10, blank=True)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "supplier_portal_invoice_item"


class PaymentRecord(TimeStamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        SupplierCompany,
        on_delete=models.CASCADE,
        related_name="payments",
        db_index=True,
    )
    store = models.ForeignKey(
        SupplierStore, on_delete=models.PROTECT, related_name="payments"
    )
    invoice = models.ForeignKey(
        OutgoingInvoice,
        on_delete=models.CASCADE,
        related_name="payments",
        null=True,
        blank=True,
    )
    invoice_number = models.CharField(max_length=50)
    store_name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_date = models.DateField()
    due_date = models.DateField()
    paid_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    days_overdue = models.IntegerField(default=0)

    class Meta:
        db_table = "supplier_portal_payment"
        indexes = [
            models.Index(fields=("supplier", "status")),
            models.Index(fields=("supplier", "-days_overdue")),
        ]
        ordering = ("-days_overdue",)


class DemandSignal(TimeStamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        SupplierCompany,
        on_delete=models.CASCADE,
        related_name="demand_signals",
        db_index=True,
    )
    product = models.ForeignKey(
        SupplierProduct, on_delete=models.SET_NULL, null=True, blank=True
    )
    product_name = models.CharField(max_length=200)
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100, blank=True)
    weekly_volume = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    trend_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    predicted_next_week = models.DecimalField(
        max_digits=14, decimal_places=3, default=0
    )
    hotness = models.CharField(
        max_length=20, choices=DemandHotness.choices, default=DemandHotness.STABLE
    )

    class Meta:
        db_table = "supplier_portal_demand_signal"
        indexes = [
            models.Index(fields=("supplier", "region")),
            models.Index(fields=("supplier", "hotness")),
        ]


class IncomingOrder(TimeStamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        SupplierCompany,
        on_delete=models.CASCADE,
        related_name="incoming_orders",
        db_index=True,
    )
    store = models.ForeignKey(
        SupplierStore, on_delete=models.PROTECT, related_name="incoming_orders"
    )
    store_name = models.CharField(max_length=200)
    number = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20,
        choices=IncomingOrderStatus.choices,
        default=IncomingOrderStatus.PENDING,
    )
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    requested_at = models.DateTimeField(auto_now_add=True)
    rejection_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "supplier_portal_incoming_order"
        indexes = [
            models.Index(fields=("supplier", "status")),
            models.Index(fields=("supplier", "-requested_at")),
        ]
        ordering = ("-requested_at",)


class IncomingOrderItem(TimeStamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        IncomingOrder, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        SupplierProduct, on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField(max_length=200)
    mxik = models.CharField(max_length=10, blank=True)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "supplier_portal_incoming_order_item"


class DeliveryRoute(TimeStamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(
        SupplierCompany,
        on_delete=models.CASCADE,
        related_name="routes",
        db_index=True,
    )
    driver_name = models.CharField(max_length=200)
    vehicle_plate = models.CharField(max_length=20)
    started_at = models.DateTimeField(null=True, blank=True)
    estimated_completion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "supplier_portal_route"
        ordering = ("-created_at",)


class DeliveryRouteStop(TimeStamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    route = models.ForeignKey(
        DeliveryRoute, on_delete=models.CASCADE, related_name="stops"
    )
    store = models.ForeignKey(
        SupplierStore, on_delete=models.PROTECT, related_name="route_stops"
    )
    store_name = models.CharField(max_length=200)
    eta = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=DeliveryStopStatus.choices,
        default=DeliveryStopStatus.PENDING,
    )
    order_index = models.IntegerField(default=0)

    class Meta:
        db_table = "supplier_portal_route_stop"
        ordering = ("order_index",)
