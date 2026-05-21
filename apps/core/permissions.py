"""
Tenant-aware permission classes for DRF.

All non-public views require an authenticated user AND an active store
context. Role gates compose on top of HasActiveStore.
"""

from __future__ import annotations

from rest_framework import permissions

from apps.accounts.models import Role


def _payload(request) -> dict | None:
    auth = getattr(request, "auth", None)
    return getattr(auth, "payload", None) if auth is not None else None


def resolve_active_store_id(request) -> str | None:
    """Pull active_store_id from JWT payload and cache on request.

    Called by permission classes — must run after DRF auth, since
    classic Django middleware fires before request.auth is populated.

    Backwards-compat: prefers explicit `active_store_id`; also reads
    `active_tenant_id` when `active_portal == "store"`.
    """
    cached = getattr(request, "active_store_id", None)
    if cached:
        return cached
    payload = _payload(request)
    sid = payload.get("active_store_id") if payload else None
    if sid is None and payload is not None:
        if payload.get("active_portal") == "store":
            sid = payload.get("active_tenant_id")
    request.active_store_id = sid
    return sid


def resolve_active_supplier_id(request) -> str | None:
    """Pull active_tenant_id from JWT for supplier portal and cache it."""
    cached = getattr(request, "active_supplier_id", None)
    if cached:
        return cached
    payload = _payload(request)
    if not payload:
        return None
    if payload.get("active_portal") != "supplier":
        return None
    sid = payload.get("active_tenant_id")
    request.active_supplier_id = sid
    return sid


class HasActiveStore(permissions.BasePermission):
    message = "Faol do'kon tanlanmagan."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(resolve_active_store_id(request))


class HasActiveSupplier(permissions.BasePermission):
    """Distribyutor portal counterpart to HasActiveStore.

    Verifies JWT has active_portal='supplier' + a tenant_id, then checks
    the user holds an active supplier membership against that tenant.
    """

    message = "Faol distribyutor tanlanmagan."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        supplier_id = resolve_active_supplier_id(request)
        if not supplier_id:
            return False
        from apps.accounts.models import Membership, MembershipStatus, Portal

        membership = Membership.objects.filter(
            user=request.user,
            portal=Portal.SUPPLIER,
            tenant_id=supplier_id,
            status=MembershipStatus.ACTIVE,
        ).only("role").first()
        if membership is None:
            return False
        request._active_supplier_role = membership.role
        return True


class RolePermission(HasActiveStore):
    """Subclass with REQUIRED_ROLES set to the roles allowed to act."""

    required_roles: tuple[str, ...] = ()
    safe_roles: tuple[str, ...] = ()  # roles allowed for GET/HEAD/OPTIONS

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        role = self._role_for(request)
        if role is None:
            return False
        if request.method in permissions.SAFE_METHODS and self.safe_roles:
            return role in self.safe_roles or role in self.required_roles
        return role in self.required_roles

    @staticmethod
    def _role_for(request) -> str | None:
        from apps.accounts.models import Membership

        cached = getattr(request, "_active_role", None)
        if cached is not None:
            return cached
        store_id = getattr(request, "active_store_id", None)
        if not store_id:
            return None
        membership = (
            Membership.objects.filter(
                user=request.user, store_id=store_id, status="active"
            )
            .only("role")
            .first()
        )
        request._active_role = membership.role if membership else None
        return request._active_role


class IsAdmin(RolePermission):
    required_roles = (Role.ADMIN,)


class CanApproveDocuments(RolePermission):
    required_roles = (Role.ADMIN, Role.OMBORCHI)
    safe_roles = (Role.BUXGALTER, Role.AUDITOR)


class CanEditCatalog(RolePermission):
    """Products / suppliers / nomenklatura."""

    required_roles = (Role.ADMIN, Role.OMBORCHI)
    safe_roles = (Role.BUXGALTER, Role.AUDITOR, Role.KASSIR)


class CanViewReports(RolePermission):
    required_roles = (Role.ADMIN, Role.BUXGALTER, Role.AUDITOR)


class ReadOnlyForAuditor(RolePermission):
    """Auditors get read across the system, no writes."""

    required_roles = (Role.ADMIN,)
    safe_roles = tuple(r for r, _ in Role.choices)
