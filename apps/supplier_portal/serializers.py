"""DRF serializers for the supplier portal.

Field naming uses snake_case; the frontend layer converts to camelCase.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.core.validators import normalize_stir

from .models import (
    DeliveryRoute,
    DeliveryRouteStop,
    DemandSignal,
    IncomingOrder,
    IncomingOrderItem,
    OutgoingInvoice,
    OutgoingInvoiceItem,
    PaymentRecord,
    SupplierCompany,
    SupplierProduct,
    SupplierStore,
)


class SupplierCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierCompany
        fields = (
            "id",
            "name",
            "stir",
            "director",
            "phone",
            "email",
            "address",
            "brand_type",
            "region",
            "fleet_size",
            "warehouse_address",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "stir", "created_at", "updated_at")


class SupplierStoreSerializer(serializers.ModelSerializer):
    supplier_id = serializers.UUIDField(source="supplier.id", read_only=True)

    class Meta:
        model = SupplierStore
        fields = (
            "id",
            "supplier_id",
            "store_id",
            "name",
            "stir",
            "director",
            "phone",
            "region",
            "district",
            "status",
            "reliability_score",
            "monthly_volume",
            "total_lifetime_volume",
            "last_order_at",
            "credit_limit",
            "outstanding_balance",
            "joined_at",
            "growth_percent",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "supplier_id",
            "joined_at",
            "created_at",
            "updated_at",
        )

    def validate_stir(self, value: str) -> str:
        try:
            return normalize_stir(value)
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc


class SupplierProductSerializer(serializers.ModelSerializer):
    supplier_id = serializers.UUIDField(source="supplier.id", read_only=True)

    class Meta:
        model = SupplierProduct
        fields = (
            "id",
            "supplier_id",
            "name",
            "mxik",
            "category",
            "unit",
            "base_price",
            "stock",
            "monthly_sales",
            "trend_percent",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "supplier_id", "created_at", "updated_at")


class OutgoingInvoiceItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(
        source="product.id", read_only=True, default=None
    )

    class Meta:
        model = OutgoingInvoiceItem
        fields = (
            "id",
            "product_id",
            "name",
            "mxik",
            "unit",
            "quantity",
            "price",
            "total",
        )
        read_only_fields = ("id", "product_id", "total")


class OutgoingInvoiceSerializer(serializers.ModelSerializer):
    items = OutgoingInvoiceItemSerializer(many=True, read_only=True)
    supplier_id = serializers.UUIDField(source="supplier.id", read_only=True)
    store_id = serializers.UUIDField(source="store.id", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = OutgoingInvoice
        fields = (
            "id",
            "supplier_id",
            "store_id",
            "store_name",
            "number",
            "status",
            "items",
            "total_amount",
            "sent_at",
            "due_date",
            "paid_at",
            "tracking_note",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CreateInvoiceItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=False, allow_null=True)
    name = serializers.CharField(max_length=200)
    mxik = serializers.CharField(max_length=10, required=False, allow_blank=True)
    unit = serializers.CharField(max_length=20)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    price = serializers.DecimalField(max_digits=14, decimal_places=2)


class CreateInvoiceSerializer(serializers.Serializer):
    store_id = serializers.UUIDField()
    items = CreateInvoiceItemSerializer(many=True, min_length=1)
    due_date = serializers.DateField(required=False, allow_null=True)
    tracking_note = serializers.CharField(
        max_length=300, required=False, allow_blank=True
    )


class PaymentRecordSerializer(serializers.ModelSerializer):
    supplier_id = serializers.UUIDField(source="supplier.id", read_only=True)
    store_id = serializers.UUIDField(source="store.id", read_only=True)
    invoice_id = serializers.UUIDField(
        source="invoice.id", read_only=True, default=None
    )

    class Meta:
        model = PaymentRecord
        fields = (
            "id",
            "supplier_id",
            "store_id",
            "invoice_id",
            "invoice_number",
            "store_name",
            "amount",
            "paid_amount",
            "invoice_date",
            "due_date",
            "paid_at",
            "status",
            "method",
            "days_overdue",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DemandSignalSerializer(serializers.ModelSerializer):
    supplier_id = serializers.UUIDField(source="supplier.id", read_only=True)
    product_id = serializers.UUIDField(
        source="product.id", read_only=True, default=None
    )

    class Meta:
        model = DemandSignal
        fields = (
            "id",
            "supplier_id",
            "product_id",
            "product_name",
            "region",
            "district",
            "weekly_volume",
            "trend_percent",
            "predicted_next_week",
            "hotness",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "supplier_id", "created_at", "updated_at")


class IncomingOrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(
        source="product.id", read_only=True, default=None
    )

    class Meta:
        model = IncomingOrderItem
        fields = (
            "id",
            "product_id",
            "name",
            "mxik",
            "unit",
            "quantity",
            "price",
            "total",
        )
        read_only_fields = fields


class IncomingOrderSerializer(serializers.ModelSerializer):
    items = IncomingOrderItemSerializer(many=True, read_only=True)
    supplier_id = serializers.UUIDField(source="supplier.id", read_only=True)
    store_id = serializers.UUIDField(source="store.id", read_only=True)

    class Meta:
        model = IncomingOrder
        fields = (
            "id",
            "supplier_id",
            "store_id",
            "store_name",
            "number",
            "items",
            "total_amount",
            "requested_at",
            "status",
            "rejection_reason",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DeliveryRouteStopSerializer(serializers.ModelSerializer):
    store_id = serializers.UUIDField(source="store.id", read_only=True)

    class Meta:
        model = DeliveryRouteStop
        fields = (
            "id",
            "store_id",
            "store_name",
            "eta",
            "status",
            "order_index",
        )
        read_only_fields = fields


class DeliveryRouteSerializer(serializers.ModelSerializer):
    stops = DeliveryRouteStopSerializer(many=True, read_only=True)
    supplier_id = serializers.UUIDField(source="supplier.id", read_only=True)

    class Meta:
        model = DeliveryRoute
        fields = (
            "id",
            "supplier_id",
            "driver_name",
            "vehicle_plate",
            "stops",
            "started_at",
            "estimated_completion",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "supplier_id", "created_at", "updated_at")
