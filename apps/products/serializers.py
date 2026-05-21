from rest_framework import serializers

from .models import Product, StockMovement, StockMovementKind


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            "id",
            "store",
            "org",
            "name",
            "mxik",
            "unit",
            "current_stock",
            "min_stock",
            "avg_price",
            "last_received_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "store",
            "org",
            "last_received_at",
            "created_at",
            "updated_at",
        )


class StockMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockMovement
        fields = (
            "id",
            "product",
            "kind",
            "delta",
            "before",
            "after",
            "reason",
            "actor",
            "document_id",
            "created_at",
        )
        read_only_fields = fields


class StockAdjustSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[
            StockMovementKind.KIRIM,
            StockMovementKind.CHIQIM,
            StockMovementKind.INVENTARIZATSIYA,
        ]
    )
    qty = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)
    reason = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
