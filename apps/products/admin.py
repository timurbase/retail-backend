from django.contrib import admin

from .models import Product, StockMovement


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "mxik",
        "unit",
        "current_stock",
        "min_stock",
        "avg_price",
        "store",
    )
    search_fields = ("name", "mxik")
    list_filter = ("unit",)
    readonly_fields = ("id", "created_at", "updated_at", "last_received_at")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "kind", "delta", "before", "after", "actor", "created_at")
    list_filter = ("kind",)
    search_fields = ("product__name", "reason")
    readonly_fields = tuple(f.name for f in StockMovement._meta.fields)
