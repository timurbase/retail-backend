from django.contrib import admin

from .models import CompanyInfo, Org, SoliqOffice, Store


@admin.register(Org)
class OrgAdmin(admin.ModelAdmin):
    list_display = ("name", "stir", "created_at")
    search_fields = ("name", "stir")


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "org", "created_at")
    list_filter = ("plan",)
    search_fields = ("name",)


@admin.register(CompanyInfo)
class CompanyInfoAdmin(admin.ModelAdmin):
    list_display = ("name", "stir", "stir_verified", "director", "phone")
    search_fields = ("name", "stir", "director")
    list_filter = ("stir_verified",)


@admin.register(SoliqOffice)
class SoliqOfficeAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "created_at")
    search_fields = ("name",)
