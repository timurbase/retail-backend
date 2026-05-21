from django.contrib import admin

from .models import (
    DeliveryRoute,
    DeliveryRouteStop,
    DemandSignal,
    IncomingOrder,
    IncomingOrderItem,
    OutgoingInvoice,
    OutgoingInvoiceItem,
    PaymentRecord,
    SupplierCompany,
    SupplierProduct,
    SupplierStore,
)


@admin.register(SupplierCompany)
class SupplierCompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "stir", "region", "brand_type", "created_at")
    search_fields = ("name", "stir")


@admin.register(SupplierStore)
class SupplierStoreAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "stir",
        "supplier",
        "status",
        "reliability_score",
        "monthly_volume",
    )
    list_filter = ("status", "region")
    search_fields = ("name", "stir")


@admin.register(SupplierProduct)
class SupplierProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "base_price", "stock", "supplier")
    list_filter = ("category",)
    search_fields = ("name", "mxik")


class OutgoingInvoiceItemInline(admin.TabularInline):
    model = OutgoingInvoiceItem
    extra = 0


@admin.register(OutgoingInvoice)
class OutgoingInvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "supplier", "store", "status", "total_amount", "created_at")
    list_filter = ("status",)
    search_fields = ("number",)
    inlines = (OutgoingInvoiceItemInline,)


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "store_name",
        "amount",
        "status",
        "days_overdue",
    )
    list_filter = ("status", "method")


@admin.register(DemandSignal)
class DemandSignalAdmin(admin.ModelAdmin):
    list_display = ("product_name", "region", "hotness", "trend_percent")
    list_filter = ("hotness", "region")


class IncomingOrderItemInline(admin.TabularInline):
    model = IncomingOrderItem
    extra = 0


@admin.register(IncomingOrder)
class IncomingOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "supplier", "store_name", "status", "total_amount")
    list_filter = ("status",)
    search_fields = ("number", "store_name")
    inlines = (IncomingOrderItemInline,)


class DeliveryRouteStopInline(admin.TabularInline):
    model = DeliveryRouteStop
    extra = 0


@admin.register(DeliveryRoute)
class DeliveryRouteAdmin(admin.ModelAdmin):
    list_display = ("driver_name", "vehicle_plate", "supplier", "started_at")
    inlines = (DeliveryRouteStopInline,)
