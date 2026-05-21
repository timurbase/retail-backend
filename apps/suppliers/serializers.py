from rest_framework import serializers

from apps.core.validators import normalize_stir

from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = (
            "id",
            "store",
            "org",
            "name",
            "stir",
            "verified",
            "soliq_last_checked",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "store", "org", "created_at", "updated_at")

    def validate_stir(self, value: str) -> str:
        try:
            return normalize_stir(value)
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        # Enforce uniqueness within store on create/update — UniqueTogether
        # in Meta only fires when both fields are populated by the serializer;
        # store is stamped server-side, so we do it explicitly here.
        request = self.context.get("request")
        store_id = getattr(request, "active_store_id", None) if request else None
        stir = attrs.get("stir") or (self.instance.stir if self.instance else None)
        if store_id and stir:
            qs = Supplier.objects.filter(store_id=store_id, stir=stir)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"stir": "Bu STIR allaqachon ro'yxatda mavjud."}
                )
        return attrs
