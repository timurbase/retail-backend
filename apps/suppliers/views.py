"""
Supplier directory endpoints.

Mirrors lib/store.ts → {get,create,update,delete}Supplier and the
SupplierFormModal Soliq.uz lookup mock.
"""

from __future__ import annotations

from django_filters import rest_framework as filters
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.recorder import record
from apps.core.permissions import CanEditCatalog, HasActiveStore
from apps.core.validators import normalize_stir
from apps.core.viewsets import TenantScopedViewSet

from .models import Supplier
from .serializers import SupplierSerializer

MOCK_NAME_POOL_3X = (
    "Alpha Distribution OOO",
    "Beta Trade MChJ",
    "Lazzat MChJ",
    "Mineralka OOO",
)


def mock_korxona_name(stir: str) -> str:
    """Mirror /web/components/suppliers/supplier-form-modal.tsx."""
    if stir.startswith("3"):
        idx = int(stir[-1]) % len(MOCK_NAME_POOL_3X)
        return MOCK_NAME_POOL_3X[idx]
    return f"Korxona STIR-{stir}"


class SupplierFilter(filters.FilterSet):
    verified = filters.BooleanFilter()
    search = filters.CharFilter(method="search_filter")

    class Meta:
        model = Supplier
        fields = ("verified", "search")

    def search_filter(self, queryset, name, value):
        if not value:
            return queryset
        from django.db.models import Q

        return queryset.filter(Q(name__icontains=value) | Q(stir__icontains=value))


class SupplierViewSet(TenantScopedViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    filterset_class = SupplierFilter
    search_fields = ("name", "stir")
    ordering_fields = ("name", "created_at", "verified")
    ordering = ("name",)

    def get_permissions(self):
        if self.action in ("list", "retrieve", "lookup_stir"):
            return [HasActiveStore()]
        return [CanEditCatalog()]

    def perform_create(self, serializer):
        instance = serializer.save(store_id=self.request.active_store_id)
        record(
            self.request,
            action="create",
            object_type="supplier",
            object_id=str(instance.id),
            object_label=instance.name,
            details=f"STIR {instance.stir}",
        )

    def perform_update(self, serializer):
        before = SupplierSerializer(serializer.instance).data
        instance = serializer.save()
        after = SupplierSerializer(instance).data
        changes = [
            f"{k}: {before.get(k)} → {after.get(k)}"
            for k in after
            if before.get(k) != after.get(k)
        ]
        record(
            self.request,
            action="update",
            object_type="supplier",
            object_id=str(instance.id),
            object_label=instance.name,
            details="; ".join(changes) or "tahrirlandi",
        )

    def perform_destroy(self, instance):
        label = instance.name
        oid = str(instance.id)
        instance.delete()
        record(
            self.request,
            action="delete",
            object_type="supplier",
            object_id=oid,
            object_label=label,
            details="Yetkazib beruvchi o'chirildi",
        )

    @action(detail=False, methods=["get"], url_path="lookup-stir")
    def lookup_stir(self, request):
        """Mock Soliq.uz STIR lookup.

        STIRs starting with "3" return a mock korxona name + verified=True.
        Others 404.
        """
        raw = request.query_params.get("stir", "")
        try:
            stir = normalize_stir(raw)
        except Exception as exc:
            return Response({"stir": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not stir.startswith("3"):
            return Response(
                {"detail": "STIR Soliq.uz bazasida topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {
                "stir": stir,
                "name": mock_korxona_name(stir),
                "verified": True,
                "status": "Faol",
            }
        )
