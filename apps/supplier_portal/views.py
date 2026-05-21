"""Supplier portal API views.

All endpoints scoped via HasActiveSupplier — request.active_supplier_id
is resolved from the JWT active_tenant_id + active_portal='supplier' claim.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import status, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.recorder import record
from apps.core.permissions import HasActiveSupplier

from .models import (
    DeliveryRoute,
    DemandSignal,
    IncomingOrder,
    IncomingOrderStatus,
    OutgoingInvoice,
    OutgoingInvoiceItem,
    OutgoingInvoiceStatus,
    PaymentMethod,
    PaymentRecord,
    PaymentStatus,
    SupplierCompany,
    SupplierProduct,
    SupplierStore,
)
from .serializers import (
    CreateInvoiceSerializer,
    DeliveryRouteSerializer,
    DemandSignalSerializer,
    IncomingOrderSerializer,
    OutgoingInvoiceSerializer,
    PaymentRecordSerializer,
    SupplierCompanySerializer,
    SupplierProductSerializer,
    SupplierStoreSerializer,
)


def _audit(request, **kwargs):
    """Record an audit entry, dropping store_id since tenant column is a real
    FK to tenants.Store and supplier portal tenants don't live there.

    Supplier tenant context is embedded in details/extra so reports can
    still partition by supplier in queries.
    """
    extra = kwargs.pop("extra", {}) or {}
    extra["supplier_id"] = str(getattr(request, "active_supplier_id", "") or "")
    return record(request, store_id=None, extra=extra, **kwargs)


# ---------- Company (singleton) ------------------------------------------


class SupplierCompanyView(views.APIView):
    permission_classes = (HasActiveSupplier,)

    def _company(self, request) -> SupplierCompany:
        return get_object_or_404(SupplierCompany, id=request.active_supplier_id)

    def get(self, request):
        return Response(SupplierCompanySerializer(self._company(request)).data)

    def patch(self, request):
        company = self._company(request)
        ser = SupplierCompanySerializer(company, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        before = SupplierCompanySerializer(company).data
        ser.save()
        after = ser.data
        changes = [
            f"{k}: {before[k]} → {after[k]}"
            for k in after
            if before.get(k) != after.get(k)
        ]
        _audit(
            request,
            action="update",
            object_type="company",
            object_id=str(company.id),
            object_label=company.name,
            details="; ".join(changes) or "tahrirlandi",
        )
        return Response(after)


# ---------- Stores --------------------------------------------------------


class SupplierStoreFilter(filters.FilterSet):
    status = filters.CharFilter()
    region = filters.CharFilter()
    search = filters.CharFilter(method="search_filter")

    class Meta:
        model = SupplierStore
        fields = ("status", "region", "search")

    def search_filter(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(Q(name__icontains=value) | Q(stir__icontains=value))


class SupplierScopedViewSet(viewsets.ModelViewSet):
    """Base ViewSet that scopes to request.active_supplier_id."""

    permission_classes = (HasActiveSupplier,)
    supplier_field = "supplier_id"

    def get_queryset(self):
        qs = super().get_queryset()
        sid = getattr(self.request, "active_supplier_id", None)
        return qs.filter(**{self.supplier_field: sid}) if sid else qs.none()

    def perform_create(self, serializer):
        serializer.save(supplier_id=self.request.active_supplier_id)


class SupplierStoreViewSet(SupplierScopedViewSet):
    queryset = SupplierStore.objects.all()
    serializer_class = SupplierStoreSerializer
    filterset_class = SupplierStoreFilter
    ordering_fields = (
        "name",
        "last_order_at",
        "monthly_volume",
        "reliability_score",
        "created_at",
    )
    ordering = ("name",)

    def perform_create(self, serializer):
        instance = serializer.save(supplier_id=self.request.active_supplier_id)
        _audit(
            self.request,
            action="create",
            object_type="store",
            object_id=str(instance.id),
            object_label=instance.name,
            details=f"Mijoz do'kon qo'shildi · STIR {instance.stir}",
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        _audit(
            self.request,
            action="update",
            object_type="store",
            object_id=str(instance.id),
            object_label=instance.name,
            details="Do'kon ma'lumotlari yangilandi",
        )

    def perform_destroy(self, instance):
        label = instance.name
        oid = str(instance.id)
        instance.delete()
        _audit(
            self.request,
            action="delete",
            object_type="store",
            object_id=oid,
            object_label=label,
            details="Mijoz do'kon o'chirildi",
        )

    @action(detail=True, methods=["post"], url_path="credit-limit")
    def credit_limit(self, request, pk=None):
        instance = self.get_object()
        try:
            limit = Decimal(str(request.data.get("limit", "0")))
        except Exception:
            return Response(
                {"error": "limit raqam bo'lishi kerak"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        before = instance.credit_limit
        instance.credit_limit = limit
        instance.save(update_fields=("credit_limit", "updated_at"))
        _audit(
            request,
            action="update",
            object_type="store",
            object_id=str(instance.id),
            object_label=instance.name,
            details=f"credit_limit: {before} → {limit}",
        )
        return Response(SupplierStoreSerializer(instance).data)


# ---------- Products ------------------------------------------------------


class SupplierProductFilter(filters.FilterSet):
    category = filters.CharFilter()
    search = filters.CharFilter(method="search_filter")

    class Meta:
        model = SupplierProduct
        fields = ("category", "search")

    def search_filter(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(Q(name__icontains=value) | Q(mxik__icontains=value))


class SupplierProductViewSet(SupplierScopedViewSet):
    queryset = SupplierProduct.objects.all()
    serializer_class = SupplierProductSerializer
    filterset_class = SupplierProductFilter
    ordering_fields = ("name", "monthly_sales", "trend_percent", "stock", "created_at")
    ordering = ("name",)


# ---------- Invoices ------------------------------------------------------


class OutgoingInvoiceFilter(filters.FilterSet):
    status = filters.CharFilter()
    store = filters.UUIDFilter(field_name="store_id")
    from_date = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    to_date = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    search = filters.CharFilter(method="search_filter")

    class Meta:
        model = OutgoingInvoice
        fields = ("status", "store", "from_date", "to_date", "search")

    def search_filter(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(Q(number__icontains=value) | Q(store__name__icontains=value))


def _invoice_prefix(name: str) -> str:
    letters = "".join(c for c in name.upper() if c.isalpha())[:3]
    return letters or "INV"


def _next_invoice_number(supplier: SupplierCompany) -> str:
    year = timezone.now().year
    prefix = _invoice_prefix(supplier.name)
    count = OutgoingInvoice.objects.filter(supplier=supplier).count() + 1
    return f"{prefix}-{year}-{count:04d}"


class OutgoingInvoiceViewSet(viewsets.ModelViewSet):
    permission_classes = (HasActiveSupplier,)
    queryset = OutgoingInvoice.objects.select_related("store").prefetch_related("items")
    serializer_class = OutgoingInvoiceSerializer
    filterset_class = OutgoingInvoiceFilter
    ordering_fields = ("created_at", "total_amount", "due_date")
    ordering = ("-created_at",)

    def get_queryset(self):
        sid = getattr(self.request, "active_supplier_id", None)
        if not sid:
            return self.queryset.none()
        return self.queryset.filter(supplier_id=sid)

    def create(self, request, *args, **kwargs):
        ser = CreateInvoiceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        supplier = get_object_or_404(
            SupplierCompany, id=request.active_supplier_id
        )
        store = get_object_or_404(
            SupplierStore, id=data["store_id"], supplier=supplier
        )

        with transaction.atomic():
            invoice = OutgoingInvoice.objects.create(
                supplier=supplier,
                store=store,
                number=_next_invoice_number(supplier),
                status=OutgoingInvoiceStatus.DRAFT,
                due_date=data.get("due_date"),
                tracking_note=data.get("tracking_note", ""),
            )
            total = Decimal("0")
            for item in data["items"]:
                line_total = Decimal(item["quantity"]) * Decimal(item["price"])
                product = None
                if item.get("product_id"):
                    product = SupplierProduct.objects.filter(
                        id=item["product_id"], supplier=supplier
                    ).first()
                OutgoingInvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    name=item["name"],
                    mxik=item.get("mxik", ""),
                    unit=item["unit"],
                    quantity=item["quantity"],
                    price=item["price"],
                    total=line_total,
                )
                total += line_total
            invoice.total_amount = total
            invoice.save(update_fields=("total_amount", "updated_at"))

        _audit(
            request,
            action="create",
            object_type="invoice",
            object_id=str(invoice.id),
            object_label=invoice.number,
            details=f"Hisob-faktura {invoice.number} yaratildi · {store.name}",
        )
        return Response(
            OutgoingInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status not in (
            OutgoingInvoiceStatus.DRAFT,
            OutgoingInvoiceStatus.CANCELLED,
        ):
            return Response(
                {"error": "Faqat qoralama yoki bekor qilingan hisob-fakturani o'chirish mumkin"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        label = instance.number
        oid = str(instance.id)
        instance.delete()
        _audit(
            request,
            action="delete",
            object_type="invoice",
            object_id=oid,
            object_label=label,
            details="Hisob-faktura o'chirildi",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="mark-delivered")
    def mark_delivered(self, request, pk=None):
        invoice = self.get_object()
        invoice.status = OutgoingInvoiceStatus.DELIVERED
        note = request.data.get("tracking_note")
        if note:
            invoice.tracking_note = str(note)[:300]
        invoice.save(update_fields=("status", "tracking_note", "updated_at"))
        _audit(
            request,
            action="update",
            object_type="invoice",
            object_id=str(invoice.id),
            object_label=invoice.number,
            details="Yetkazib berildi deb belgilandi",
        )
        return Response(OutgoingInvoiceSerializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        method = request.data.get("method", "")
        valid_methods = {c for c, _ in PaymentMethod.choices}
        if method and method not in valid_methods:
            return Response(
                {"error": "method noto'g'ri"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            now = timezone.now()
            invoice.status = OutgoingInvoiceStatus.PAID
            invoice.paid_at = now
            invoice.save(update_fields=("status", "paid_at", "updated_at"))

            PaymentRecord.objects.create(
                supplier=invoice.supplier,
                store=invoice.store,
                invoice=invoice,
                invoice_number=invoice.number,
                store_name=invoice.store.name,
                amount=invoice.total_amount,
                paid_amount=invoice.total_amount,
                invoice_date=invoice.created_at.date(),
                due_date=invoice.due_date or invoice.created_at.date(),
                paid_at=now,
                status=PaymentStatus.PAID,
                method=method or "",
                days_overdue=0,
            )

        _audit(
            request,
            action="update",
            object_type="invoice",
            object_id=str(invoice.id),
            object_label=invoice.number,
            details=f"To'lov qabul qilindi · {method or 'noma''lum'}",
        )
        return Response(OutgoingInvoiceSerializer(invoice).data)


# ---------- Incoming orders ----------------------------------------------


class IncomingOrderFilter(filters.FilterSet):
    status = filters.CharFilter()
    search = filters.CharFilter(method="search_filter")

    class Meta:
        model = IncomingOrder
        fields = ("status", "search")

    def search_filter(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(Q(number__icontains=value) | Q(store_name__icontains=value))


class IncomingOrderViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (HasActiveSupplier,)
    queryset = IncomingOrder.objects.prefetch_related("items").select_related("store")
    serializer_class = IncomingOrderSerializer
    filterset_class = IncomingOrderFilter
    ordering = ("-requested_at",)

    def get_queryset(self):
        sid = getattr(self.request, "active_supplier_id", None)
        if not sid:
            return self.queryset.none()
        return self.queryset.filter(supplier_id=sid)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        order = self.get_object()
        if order.status != IncomingOrderStatus.PENDING:
            return Response(
                {"error": "Faqat kutilayotgan buyurtmani qabul qilish mumkin"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        create_invoice = bool(request.data.get("create_invoice", True))

        with transaction.atomic():
            order.status = IncomingOrderStatus.ACCEPTED
            order.save(update_fields=("status", "updated_at"))

            invoice = None
            if create_invoice:
                supplier = order.supplier
                invoice = OutgoingInvoice.objects.create(
                    supplier=supplier,
                    store=order.store,
                    number=_next_invoice_number(supplier),
                    status=OutgoingInvoiceStatus.PREPARING,
                    total_amount=order.total_amount,
                )
                for item in order.items.all():
                    OutgoingInvoiceItem.objects.create(
                        invoice=invoice,
                        product=item.product,
                        name=item.name,
                        mxik=item.mxik,
                        unit=item.unit,
                        quantity=item.quantity,
                        price=item.price,
                        total=item.total,
                    )

        _audit(
            request,
            action="approve",
            object_type="order",
            object_id=str(order.id),
            object_label=order.number,
            details="Buyurtma qabul qilindi",
        )
        payload = IncomingOrderSerializer(order).data
        if invoice:
            payload["invoice"] = OutgoingInvoiceSerializer(invoice).data
        return Response(payload)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        order = self.get_object()
        reason = (request.data.get("reason") or "").strip()
        if not reason:
            return Response(
                {"error": "Rad etish sababini ko'rsating"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = IncomingOrderStatus.REJECTED
        order.rejection_reason = reason[:300]
        order.save(update_fields=("status", "rejection_reason", "updated_at"))
        _audit(
            request,
            action="reject",
            object_type="order",
            object_id=str(order.id),
            object_label=order.number,
            details=f"Rad etildi: {reason[:200]}",
        )
        return Response(IncomingOrderSerializer(order).data)


# ---------- Payments ------------------------------------------------------


AGING_BUCKETS = (
    ("0-30", 0, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("90+", 91, 10_000),
)


def _refresh_overdue_days(qs):
    today = date.today()
    for p in qs:
        if p.status == PaymentStatus.PAID:
            continue
        new_days = max(0, (today - p.due_date).days)
        if new_days != p.days_overdue:
            p.days_overdue = new_days
            if new_days > 0 and p.status == PaymentStatus.PENDING:
                p.status = PaymentStatus.OVERDUE
            PaymentRecord.objects.filter(pk=p.pk).update(
                days_overdue=p.days_overdue, status=p.status
            )


class PaymentRecordFilter(filters.FilterSet):
    status = filters.CharFilter()
    aging = filters.CharFilter(method="aging_filter")
    search = filters.CharFilter(method="search_filter")

    class Meta:
        model = PaymentRecord
        fields = ("status", "aging", "search")

    def aging_filter(self, qs, name, value):
        for label, lo, hi in AGING_BUCKETS:
            if label == value:
                return qs.filter(days_overdue__gte=lo, days_overdue__lte=hi)
        return qs

    def search_filter(self, qs, name, value):
        if not value:
            return qs
        return qs.filter(
            Q(invoice_number__icontains=value) | Q(store_name__icontains=value)
        )


class PaymentRecordViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (HasActiveSupplier,)
    queryset = PaymentRecord.objects.select_related("store", "invoice")
    serializer_class = PaymentRecordSerializer
    filterset_class = PaymentRecordFilter
    ordering_fields = ("days_overdue", "due_date", "amount")
    ordering = ("-days_overdue",)

    def get_queryset(self):
        sid = getattr(self.request, "active_supplier_id", None)
        if not sid:
            return self.queryset.none()
        qs = self.queryset.filter(supplier_id=sid)
        _refresh_overdue_days(list(qs.filter(~Q(status=PaymentStatus.PAID))))
        return self.queryset.filter(supplier_id=sid)

    @action(detail=False, methods=["get"])
    def aging(self, request):
        sid = request.active_supplier_id
        qs = PaymentRecord.objects.filter(supplier_id=sid).exclude(
            status=PaymentStatus.PAID
        )
        _refresh_overdue_days(list(qs))
        buckets = []
        for label, lo, hi in AGING_BUCKETS:
            bucket_qs = qs.filter(days_overdue__gte=lo, days_overdue__lte=hi)
            agg = bucket_qs.aggregate(c=Count("id"), s=Sum("amount"))
            buckets.append(
                {
                    "label": label,
                    "count": agg["c"] or 0,
                    "sum": str(agg["s"] or 0),
                }
            )
        return Response({"buckets": buckets})


# ---------- Demand signals -----------------------------------------------


class DemandSignalFilter(filters.FilterSet):
    region = filters.CharFilter()
    hotness = filters.CharFilter()

    class Meta:
        model = DemandSignal
        fields = ("region", "hotness")


class DemandSignalViewSet(SupplierScopedViewSet):
    queryset = DemandSignal.objects.all()
    serializer_class = DemandSignalSerializer
    filterset_class = DemandSignalFilter
    ordering_fields = ("trend_percent", "weekly_volume", "predicted_next_week")
    ordering = ("-trend_percent",)


# ---------- Routes --------------------------------------------------------


class DeliveryRouteViewSet(SupplierScopedViewSet):
    queryset = DeliveryRoute.objects.prefetch_related("stops__store").all()
    serializer_class = DeliveryRouteSerializer
    ordering = ("-created_at",)


# ---------- KPI + insights -----------------------------------------------


class KpiDashboardView(views.APIView):
    permission_classes = (HasActiveSupplier,)

    def get(self, request):
        sid = request.active_supplier_id
        stores = SupplierStore.objects.filter(supplier_id=sid)
        active_stores = stores.filter(status="active").count()
        total_stores = stores.count()

        today = timezone.now().date()
        today_invoices = OutgoingInvoice.objects.filter(
            supplier_id=sid, created_at__date=today
        ).count()

        outstanding = (
            PaymentRecord.objects.filter(supplier_id=sid)
            .exclude(status=PaymentStatus.PAID)
            .aggregate(s=Sum("amount"))["s"]
            or 0
        )

        since = timezone.now() - timedelta(days=30)
        monthly_revenue = (
            OutgoingInvoice.objects.filter(
                supplier_id=sid,
                created_at__gte=since,
                status__in=(
                    OutgoingInvoiceStatus.DELIVERED,
                    OutgoingInvoiceStatus.PAID,
                ),
            ).aggregate(s=Sum("total_amount"))["s"]
            or 0
        )

        return Response(
            {
                "active_stores": active_stores,
                "total_stores": total_stores,
                "today_invoices": today_invoices,
                "outstanding_payments": str(outstanding),
                "monthly_revenue": str(monthly_revenue),
            }
        )


class InsightsView(views.APIView):
    permission_classes = (HasActiveSupplier,)

    def get(self, request):
        sid = request.active_supplier_id
        now = timezone.now()
        fourteen = now - timedelta(days=14)

        churn_qs = (
            SupplierStore.objects.filter(supplier_id=sid, reliability_score__gte=7.5)
            .filter(Q(last_order_at__lt=fourteen) | Q(last_order_at__isnull=True))
            .order_by("-monthly_volume")[:5]
        )
        growth_qs = (
            SupplierStore.objects.filter(supplier_id=sid, reliability_score__gte=9.0)
            .order_by("-monthly_volume")[:5]
        )

        overdue_qs = PaymentRecord.objects.filter(
            supplier_id=sid, status=PaymentStatus.OVERDUE
        ).order_by("-days_overdue")[:5]

        region_qs = (
            DemandSignal.objects.filter(supplier_id=sid)
            .values("region")
            .annotate(trend=Avg("trend_percent"))
            .order_by("-trend")
        )
        rising_region = None
        if region_qs:
            top = region_qs[0]
            rising_region = {
                "region": top["region"],
                "trend_percent": str(top["trend"] or 0),
            }

        return Response(
            {
                "churn_risk": SupplierStoreSerializer(churn_qs, many=True).data,
                "growth_candidates": SupplierStoreSerializer(growth_qs, many=True).data,
                "overdue": PaymentRecordSerializer(overdue_qs, many=True).data,
                "rising_region": rising_region,
            }
        )
