"""
Retail document endpoints — CRUD + row-level actions.

Mirrors lib/store.ts → createManualDocument / approveDocument /
rejectDocument / approveRow / rejectRow / updateRowMxik /
selectVariant / bulkApproveHighConfidence / getDocumentStats.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import status, views
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.recorder import record
from apps.core.permissions import CanApproveDocuments, HasActiveStore
from apps.core.viewsets import TenantScopedViewSet
from apps.products.models import Product, StockMovement, StockMovementKind
from apps.suppliers.models import Supplier

from .models import (
    DocumentStatus,
    ProductRow,
    ProductRowStatus,
    RetailDocument,
)
from .serializers import (
    ManualDocInputSerializer,
    ProductRowSerializer,
    RejectSerializer,
    RetailDocumentDetailSerializer,
    RetailDocumentListSerializer,
    RowMxikUpdateSerializer,
    SelectVariantSerializer,
)


def recalc_review_count(doc: RetailDocument) -> None:
    doc.review_count = doc.rows.filter(
        status__in=[ProductRowStatus.NEW, ProductRowStatus.AMBIGUOUS]
    ).count()
    doc.save(update_fields=["review_count", "updated_at"])


class DocumentFilter(filters.FilterSet):
    status = filters.CharFilter()
    supplier = filters.UUIDFilter(field_name="supplier_id")
    source = filters.CharFilter()
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = RetailDocument
        fields = ("status", "supplier", "source", "search")

    def filter_search(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(
            Q(number__icontains=value) | Q(supplier__name__icontains=value)
        )


class DocumentViewSet(TenantScopedViewSet):
    queryset = RetailDocument.objects.select_related("supplier").all()
    filterset_class = DocumentFilter
    search_fields = ("number", "supplier__name")
    ordering_fields = ("created_at", "date", "total_amount")
    ordering = ("-created_at",)

    def get_permissions(self):
        if self.action in ("list", "retrieve", "stats"):
            return [HasActiveStore()]
        return [CanApproveDocuments()]

    def get_serializer_class(self):
        if self.action in ("list",):
            return RetailDocumentListSerializer
        return RetailDocumentDetailSerializer

    # -- CRUD ------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        # Block default create — manual creation has its own endpoint.
        return Response(
            {
                "detail": "Use POST /api/documents/manual/ for manual document creation.",
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def update(self, request, *args, **kwargs):
        return Response(
            {"detail": "Use row-level endpoints to mutate document content."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        label = f"Hujjat №{instance.number}"
        oid = str(instance.id)
        supplier_name = instance.supplier.name
        row_count = instance.rows.count()
        instance.delete()
        record(
            self.request,
            action="delete",
            object_type="document",
            object_id=oid,
            object_label=label,
            details=f"{supplier_name} dan keladigan {row_count} mahsulotli hujjat o'chirildi",
        )

    # -- Manual creation -------------------------------------------------

    @action(detail=False, methods=["post"], url_path="manual")
    def manual(self, request):
        serializer = ManualDocInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        store_id = request.active_store_id
        supplier = get_object_or_404(
            Supplier, pk=data["supplier_id"], store_id=store_id
        )

        with transaction.atomic():
            doc = RetailDocument.objects.create(
                store_id=store_id,
                number=data["number"],
                source="manual",
                supplier=supplier,
                date=data["date"],
                status=DocumentStatus.REVIEW,
                review_count=0,
                total_amount=Decimal("0"),
            )
            total = Decimal("0")
            for idx, r in enumerate(data["rows"]):
                quantity: Decimal = r["quantity"]
                price: Decimal = r["price"]
                row_total = (quantity * price).quantize(Decimal("0.01"))
                total += row_total
                mxik = (r.get("mxik") or "").strip()
                ProductRow.objects.create(
                    document=doc,
                    raw_name=r["rawName"],
                    mapped_product_id=r.get("mappedProductId"),
                    mxik_code=mxik,
                    mxik_name=r["rawName"] if mxik else "",
                    mxik_confidence=1.0 if mxik else 0.0,
                    alternatives=[],
                    unit=r["unit"],
                    quantity=quantity,
                    price=price,
                    total=row_total,
                    status=ProductRowStatus.MATCHED,
                    order_index=idx,
                )
            doc.total_amount = total
            doc.save(update_fields=["total_amount", "updated_at"])

        record(
            request,
            action="create",
            object_type="document",
            object_id=str(doc.id),
            object_label=f"Hujjat №{doc.number}",
            details=f"Qo'lda yaratildi · {supplier.name} · {len(data['rows'])} mahsulot",
        )
        return Response(
            RetailDocumentDetailSerializer(doc).data,
            status=status.HTTP_201_CREATED,
        )

    # -- Document-level actions -----------------------------------------

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        doc = self.get_object()
        with transaction.atomic():
            doc = (
                RetailDocument.objects.select_for_update()
                .select_related("supplier")
                .get(pk=doc.pk)
            )
            doc.status = DocumentStatus.APPROVED
            doc.review_count = 0
            doc.save(update_fields=["status", "review_count", "updated_at"])

            rows_to_post: list[ProductRow] = list(
                doc.rows.select_related("mapped_product").all()
            )
            for row in rows_to_post:
                if row.status == ProductRowStatus.MATCHED:
                    row.status = ProductRowStatus.APPROVED
                    row.save(update_fields=["status", "updated_at"])

                # Stock-post any approved row that has a mapped product
                if (
                    row.status == ProductRowStatus.APPROVED
                    and row.mapped_product_id is not None
                ):
                    product = Product.objects.select_for_update().get(
                        pk=row.mapped_product_id
                    )
                    before = product.current_stock
                    after = before + row.quantity
                    product.current_stock = after
                    product.last_received_at = timezone.now()
                    product.save(
                        update_fields=[
                            "current_stock",
                            "last_received_at",
                            "updated_at",
                        ]
                    )
                    StockMovement.objects.create(
                        store_id=request.active_store_id,
                        product=product,
                        kind=StockMovementKind.DOC_APPROVE,
                        delta=row.quantity,
                        before=before,
                        after=after,
                        reason=f"Hujjat №{doc.number}",
                        actor=request.user if request.user.is_authenticated else None,
                        document_id=doc.id,
                    )

        record(
            request,
            action="approve",
            object_type="document",
            object_id=str(doc.id),
            object_label=f"Hujjat №{doc.number}",
            details=f"{len(rows_to_post)} mahsulot ombarga kirim qilindi",
        )
        return Response(RetailDocumentDetailSerializer(doc).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        doc = self.get_object()
        ser = RejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reason = ser.validated_data.get("reason") or "Operator rad etdi"

        doc.status = DocumentStatus.REJECTED
        doc.save(update_fields=["status", "updated_at"])
        record(
            request,
            action="reject",
            object_type="document",
            object_id=str(doc.id),
            object_label=f"Hujjat №{doc.number}",
            details=reason,
        )
        return Response(RetailDocumentDetailSerializer(doc).data)

    @action(detail=True, methods=["post"], url_path="bulk-approve-high-confidence")
    def bulk_approve_high_confidence(self, request, pk=None):
        doc = self.get_object()
        with transaction.atomic():
            qs = doc.rows.filter(
                mxik_confidence__gte=0.9,
                status__in=[ProductRowStatus.MATCHED, ProductRowStatus.NEW],
            )
            count = qs.update(status=ProductRowStatus.APPROVED)
            recalc_review_count(doc)
        record(
            request,
            action="approve",
            object_type="document",
            object_id=str(doc.id),
            object_label=f"Hujjat №{doc.number}",
            details=f"Bulk: {count} ta yuqori-confidence qator avto-tasdiqlandi",
        )
        return Response({"count": count})

    @action(detail=False, methods=["get"])
    def stats(self, request):
        qs = self.get_queryset()
        today = timezone.localdate()
        new_today = qs.filter(created_at__date=today).count()
        review_queue = sum(qs.values_list("review_count", flat=True))

        row_qs = ProductRow.objects.filter(document__store_id=request.active_store_id)
        total_rows = row_qs.count()
        approved_rows = row_qs.filter(
            status__in=[ProductRowStatus.APPROVED, ProductRowStatus.MATCHED]
        ).count()
        auto_approval_rate = (
            (approved_rows / total_rows) if total_rows > 0 else 0
        )
        return Response(
            {
                "newToday": new_today,
                "reviewQueue": review_queue,
                "autoApprovalRate": auto_approval_rate,
                "totalRows": total_rows,
                "approvedRows": approved_rows,
            }
        )


class RowActionsView(views.APIView):
    """Row-level actions:

      POST   /api/documents/{doc_id}/rows/{row_id}/approve/
      POST   /api/documents/{doc_id}/rows/{row_id}/reject/
      PATCH  /api/documents/{doc_id}/rows/{row_id}/mxik/
      POST   /api/documents/{doc_id}/rows/{row_id}/select-variant/

    Dispatched via path kwarg `verb`.
    """

    def get_permissions(self):
        return [CanApproveDocuments()]

    def _row(self, request, doc_id, row_id) -> tuple[RetailDocument, ProductRow]:
        doc = get_object_or_404(
            RetailDocument, pk=doc_id, store_id=request.active_store_id
        )
        row = get_object_or_404(ProductRow, pk=row_id, document=doc)
        return doc, row

    def post(self, request, doc_id, row_id, verb):
        doc, row = self._row(request, doc_id, row_id)
        if verb == "approve":
            row.status = ProductRowStatus.APPROVED
            row.save(update_fields=["status", "updated_at"])
            recalc_review_count(doc)
            record(
                request,
                action="approve",
                object_type="row",
                object_id=str(row.id),
                object_label=row.raw_name,
                details=(
                    f"Hujjat №{doc.number} qator tasdiqlandi · "
                    f"MXIK {row.mxik_code or '—'}"
                ),
            )
            return Response(ProductRowSerializer(row).data)

        if verb == "reject":
            ser = RejectSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            reason = ser.validated_data.get("reason") or "Operator rad etdi"
            row.status = ProductRowStatus.REJECTED
            row.save(update_fields=["status", "updated_at"])
            recalc_review_count(doc)
            record(
                request,
                action="reject",
                object_type="row",
                object_id=str(row.id),
                object_label=row.raw_name,
                details=reason,
            )
            return Response(ProductRowSerializer(row).data)

        if verb == "select-variant":
            ser = SelectVariantSerializer(data=request.data)
            ser.is_valid(raise_exception=True)
            code = ser.validated_data["code"]
            variant = None
            for alt in row.alternatives or []:
                if isinstance(alt, dict) and alt.get("code") == code:
                    variant = alt
                    break
            if variant is None:
                return Response(
                    {"detail": "Variant topilmadi."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            row.mxik_code = variant.get("code", "")
            row.mxik_name = variant.get("name", "")
            row.mxik_confidence = float(variant.get("confidence", 0))
            row.status = ProductRowStatus.APPROVED
            row.save(
                update_fields=[
                    "mxik_code",
                    "mxik_name",
                    "mxik_confidence",
                    "status",
                    "updated_at",
                ]
            )
            recalc_review_count(doc)
            record(
                request,
                action="update",
                object_type="row",
                object_id=str(row.id),
                object_label=row.raw_name,
                details=f"MXIK variantidan tanlandi: {code}",
            )
            return Response(ProductRowSerializer(row).data)

        return Response(status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, doc_id, row_id, verb):
        if verb != "mxik":
            return Response(status=status.HTTP_404_NOT_FOUND)
        doc, row = self._row(request, doc_id, row_id)
        ser = RowMxikUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        old_code = row.mxik_code
        confidence = ser.validated_data["confidence"]
        row.mxik_code = ser.validated_data["code"]
        row.mxik_name = ser.validated_data["name"]
        row.mxik_confidence = confidence
        if confidence >= 0.9:
            row.status = ProductRowStatus.MATCHED
        elif confidence >= 0.6:
            row.status = ProductRowStatus.NEW
        else:
            row.status = ProductRowStatus.AMBIGUOUS
        row.save(
            update_fields=[
                "mxik_code",
                "mxik_name",
                "mxik_confidence",
                "status",
                "updated_at",
            ]
        )
        recalc_review_count(doc)
        record(
            request,
            action="update",
            object_type="row",
            object_id=str(row.id),
            object_label=row.raw_name,
            details=f"MXIK {old_code or '—'} → {row.mxik_code}",
        )
        return Response(ProductRowSerializer(row).data)
