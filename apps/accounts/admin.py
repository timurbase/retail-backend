from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Membership, OTPCode, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("phone", "full_name", "email", "is_staff", "is_active", "last_login")
    search_fields = ("phone", "full_name", "email")
    ordering = ("-created_at",)
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Personal", {"fields": ("full_name", "email")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Timestamps", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "full_name", "password1", "password2")}),
    )
    readonly_fields = ("last_login",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "store", "role", "status", "last_seen_at")
    list_filter = ("role", "status", "store")
    search_fields = ("user__phone", "user__full_name", "store__name")


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ("phone", "purpose", "expires_at", "consumed_at", "attempts", "created_at")
    list_filter = ("purpose",)
    search_fields = ("phone",)
    readonly_fields = ("code_hash", "created_at", "updated_at")
