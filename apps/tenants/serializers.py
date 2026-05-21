from rest_framework import serializers

from .models import CompanyInfo, Store


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ("id", "name", "plan", "mxik_confidence_threshold", "created_at")
        read_only_fields = ("id", "created_at")


class CompanyInfoSerializer(serializers.ModelSerializer):
    """STIR is read-only after creation — it's owned by Soliq.uz lookup."""

    store_id = serializers.UUIDField(source="store.id", read_only=True)

    class Meta:
        model = CompanyInfo
        fields = (
            "store_id",
            "stir",
            "stir_verified",
            "name",
            "activity",
            "address",
            "director",
            "phone",
            "email",
            "website",
        )
        read_only_fields = ("store_id", "stir", "stir_verified")
