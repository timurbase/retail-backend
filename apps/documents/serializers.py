
from rest_framework import serializers

from apps.suppliers.serializers import SupplierSerializer

from .models import ProductRow, RetailDocument


class ProductRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductRow
        fields = (
            "id",
            "document",
            "raw_name",
            "mapped_product",
            "mxik_code",
            "mxik_name",
            "mxik_confidence",
            "alternatives",
            "unit",
            "quantity",
            "price",
            "total",
            "status",
            "order_index",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "document", "created_at", "updated_at")


class RetailDocumentListSerializer(serializers.ModelSerializer):
    """List view — no rows, nested supplier."""

    supplier = SupplierSerializer(read_only=True)

    class Meta:
        model = RetailDocument
        fields = (
            "id",
            "store",
            "org",
            "number",
            "source",
            "supplier",
            "date",
            "status",
            "review_count",
            "total_amount",
            "dedup_hash",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class RetailDocumentDetailSerializer(serializers.ModelSerializer):
    """Detail view — includes all rows."""

    supplier = SupplierSerializer(read_only=True)
    rows = ProductRowSerializer(many=True, read_only=True)

    class Meta:
        model = RetailDocument
        fields = (
            "id",
            "store",
            "org",
            "number",
            "source",
            "supplier",
            "date",
            "status",
            "review_count",
            "total_amount",
            "dedup_hash",
            "rows",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ManualDocRowInputSerializer(serializers.Serializer):
    rawName = serializers.CharField(max_length=500)
    mxik = serializers.CharField(
        max_length=10, required=False, allow_null=True, allow_blank=True
    )
    unit = serializers.CharField(max_length=20)
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)
    price = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    mappedProductId = serializers.UUIDField(required=False, allow_null=True)


class ManualDocInputSerializer(serializers.Serializer):
    supplier_id = serializers.UUIDField()
    number = serializers.CharField(max_length=50)
    date = serializers.DateField()
    rows = ManualDocRowInputSerializer(many=True)


class RowMxikUpdateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=500)
    confidence = serializers.FloatField(min_value=0, max_value=1)


class SelectVariantSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10)


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
