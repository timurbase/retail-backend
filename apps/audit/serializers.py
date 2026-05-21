from rest_framework import serializers

from .models import AuditEntry


class AuditEntrySerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = AuditEntry
        fields = (
            "id",
            "timestamp",
            "user",
            "action",
            "object_type",
            "object_id",
            "object_label",
            "details",
            "ip",
        )

    def get_user(self, obj):
        # Snapshot at write time — matches frontend AuditEntry.user shape.
        snap = obj.actor_snapshot or {}
        return {
            "id": snap.get("id"),
            "name": snap.get("name"),
            "role": snap.get("role"),
        }
