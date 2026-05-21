from django.contrib import admin

from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "stir", "verified", "store", "created_at")
    list_filter = ("verified",)
    search_fields = ("name", "stir")
    readonly_fields = ("id", "created_at", "updated_at")
