from django.contrib import admin

from .models import ProductRow, RetailDocument


class ProductRowInline(admin.TabularInline):
    model = ProductRow
    extra = 0
    fields = (
        "raw_name",
        "mxik_code",
        "mxik_confidence",
        "unit",
        "quantity",
        "price",
        "total",
        "status",
    )
    readonly_fields = fields


@admin.register(RetailDocument)
class RetailDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "source",
        "supplier",
        "status",
        "review_count",
        "total_amount",
        "date",
        "store",
    )
    list_filter = ("source", "status")
    search_fields = ("number", "supplier__name")
    inlines = (ProductRowInline,)
    readonly_fields = ("id", "created_at", "updated_at", "dedup_hash")


@admin.register(ProductRow)
class ProductRowAdmin(admin.ModelAdmin):
    list_display = (
        "raw_name",
        "document",
        "mxik_code",
        "mxik_confidence",
        "status",
        "quantity",
        "price",
        "total",
    )
    list_filter = ("status",)
    search_fields = ("raw_name", "mxik_code")
    readonly_fields = ("id", "created_at", "updated_at")
