"""
Product catalog endpoints + stock adjustments + MXIK typeahead.

Mirrors lib/store.ts → {get,create,update,delete}Product, adjustStock,
getProductStats and the in-memory MXIK suggestion API.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import status, views
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.recorder import record
from apps.core.permissions import CanEditCatalog, HasActiveStore
from apps.core.viewsets import TenantScopedViewSet

from . import mxik_seed
from .models import Product, StockMovement, StockMovementKind
from .serializers import ProductSerializer, StockAdjustSerializer


class ProductFilter(filters.FilterSet):
    has_mxik = filters.BooleanFilter(method="filter_has_mxik")
    low_stock = filters.BooleanFilter(method="filter_low_stock")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = Product
        fields = ("has_mxik", "low_stock", "search")

    def filter_has_mxik(self, qs, name, value):
        if value is True:
            return qs.exclude(mxik="")
        if value is False:
            return qs.filter(mxik="")
        return qs

    def filter_low_stock(self, qs, name, value):
        if value:
            return qs.filter(current_stock__lt=F("min_stock"))
        return qs

    def filter_search(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(Q(name__icontains=value) | Q(mxik__icontains=value))


class ProductViewSet(TenantScopedViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    search_fields = ("name", "mxik")
    ordering_fields = ("name", "current_stock", "avg_price", "last_received_at")
    ordering = ("name",)

    def get_permissions(self):
        if self.action in ("list", "retrieve", "stats"):
            return [HasActiveStore()]
        return [CanEditCatalog()]

    def perform_create(self, serializer):
        instance = serializer.save(store_id=self.request.active_store_id)
        record(
            self.request,
            action="create",
            object_type="product",
            object_id=str(instance.id),
            object_label=instance.name,
            details=f"Yangi mahsulot katalogga qo'shildi · MXIK {instance.mxik or '—'}",
        )

    def perform_update(self, serializer):
        before = ProductSerializer(serializer.instance).data
        instance = serializer.save()
        after = ProductSerializer(instance).data
        changes = [
            f"{k}: {before.get(k)} → {after.get(k)}"
            for k in after
            if before.get(k) != after.get(k)
        ]
        record(
            self.request,
            action="update",
            object_type="product",
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
            object_type="product",
            object_id=oid,
            object_label=label,
            details="Katalogdan o'chirildi",
        )

    @action(detail=True, methods=["post"], url_path="stock-adjust")
    def stock_adjust(self, request, pk=None):
        product = self.get_object()
        serializer = StockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kind = serializer.validated_data["kind"]
        qty: Decimal = serializer.validated_data["qty"]
        reason = serializer.validated_data.get("reason", "")

        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product.pk)
            before = product.current_stock
            if kind == StockMovementKind.KIRIM:
                after = before + qty
                delta = qty
            elif kind == StockMovementKind.CHIQIM:
                if qty > before:
                    return Response(
                        {
                            "detail": "Mavjud zaxiradan ortiq chiqim qilib bo'lmaydi.",
                            "available": str(before),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                after = before - qty
                delta = -qty
            else:  # inventarizatsiya
                after = qty
                delta = qty - before

            product.current_stock = after
            if kind == StockMovementKind.KIRIM:
                product.last_received_at = timezone.now()
            product.save(update_fields=["current_stock", "last_received_at", "updated_at"])

            StockMovement.objects.create(
                store_id=request.active_store_id,
                product=product,
                kind=kind,
                delta=delta,
                before=before,
                after=after,
                reason=reason,
                actor=request.user if request.user.is_authenticated else None,
            )

        kind_label = {
            StockMovementKind.KIRIM: "Qo'lda kirim",
            StockMovementKind.CHIQIM: "Qo'lda chiqim",
            StockMovementKind.INVENTARIZATSIYA: "Inventarizatsiya",
        }[kind]
        details = f"{kind_label}: {before} → {after} {product.unit}"
        if reason:
            details += f" · {reason}"
        record(
            request,
            action="update",
            object_type="product",
            object_id=str(product.id),
            object_label=product.name,
            details=details,
        )
        return Response(ProductSerializer(product).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.get_queryset()
        agg = qs.aggregate(
            total=Count("id"),
            critical=Count("id", filter=Q(current_stock__lt=F("min_stock"))),
            at_min=Count("id", filter=Q(current_stock=F("min_stock"))),
            ok=Count("id", filter=Q(current_stock__gt=F("min_stock"))),
            with_mxik=Count("id", filter=~Q(mxik="")),
            without_mxik=Count("id", filter=Q(mxik="")),
        )
        return Response(
            {
                "total": agg["total"] or 0,
                "critical": agg["critical"] or 0,
                "atMin": agg["at_min"] or 0,
                "ok": agg["ok"] or 0,
                "withMxik": agg["with_mxik"] or 0,
                "withoutMxik": agg["without_mxik"] or 0,
            }
        )


class MxikSuggestView(views.APIView):
    """GET /api/mxik/?q=<text>&limit=10 — typeahead for MXIK codes.

    Mock today; pgvector-backed in production.
    """

    permission_classes = (HasActiveStore,)

    def get(self, request):
        q = request.query_params.get("q", "")
        try:
            limit = int(request.query_params.get("limit", "10"))
        except ValueError:
            limit = 10
        limit = max(1, min(50, limit))
        return Response(mxik_seed.search(q, limit=limit))
