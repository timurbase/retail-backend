from django.contrib import admin

from .models import AuditEntry


@admin.register(AuditEntry)
class AuditEntryAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "action", "object_type", "object_label", "store")
    list_filter = ("action", "object_type", "store")
    search_fields = ("object_id", "object_label", "details")
    readonly_fields = tuple(f.name for f in AuditEntry._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
