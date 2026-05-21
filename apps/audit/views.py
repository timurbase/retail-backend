from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets

from apps.core.permissions import HasActiveStore

from .models import AuditEntry
from .serializers import AuditEntrySerializer


class AuditFilter(filters.FilterSet):
    action = filters.CharFilter()
    object_type = filters.CharFilter()
    actor = filters.UUIDFilter(field_name="actor_id")
    from_date = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    to_date = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")

    class Meta:
        model = AuditEntry
        fields = ("action", "object_type", "actor", "from_date", "to_date")


class AuditEntryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only — audit is append-only by design."""

    permission_classes = (HasActiveStore,)
    serializer_class = AuditEntrySerializer
    filterset_class = AuditFilter
    search_fields = ("object_label", "details", "object_id")
    ordering_fields = ("timestamp",)
    ordering = ("-timestamp",)

    def get_queryset(self):
        return AuditEntry.objects.filter(
            store_id=self.request.active_store_id
        ).order_by("-timestamp")
