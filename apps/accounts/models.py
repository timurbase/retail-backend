"""
Accounts models.

User           — custom AUTH_USER_MODEL, identified by phone (no email/password by default).
Membership     — links User × Store with a Role (chakana team).
OTPCode        — short-lived SMS codes (hashed at rest).

Roles mirror lib/types.ts → UserRole exactly so frontend RBAC matrix
maps 1:1 to backend permissions.
"""

import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStamped


class Portal(models.TextChoices):
    """Top-level tenant type — mirrors lib/types.ts → Role."""

    STORE = "store", "Chakana do'kon"
    SUPPLIER = "supplier", "Distribyutor"
    SOLIQ = "soliq", "Soliq"


class Role(models.TextChoices):
    """User role inside a portal-specific membership.

    Naming matches lib/types.ts → UserRole exactly so the frontend's
    RBAC matrix maps 1:1 to backend permissions.
    """

    # Store portal
    ADMIN = "admin", "Administrator"
    OMBORCHI = "omborchi", "Omborchi"
    BUXGALTER = "buxgalter", "Buxgalter"
    KASSIR = "kassir", "Kassir"
    AUDITOR = "auditor", "Auditor"
    FIRMA = "firma", "Firma operatori"
    # Supplier portal
    SUPPLIER_ADMIN = "supplier_admin", "Distribyutor admin"
    SUPPLIER_SALES = "supplier_sales", "Sotuv menejer"
    SUPPLIER_LOGISTICS = "supplier_logistics", "Logistika"
    SUPPLIER_BUXGALTER = "supplier_buxgalter", "Distribyutor buxgalter"
    # Soliq portal
    SOLIQ_INSPECTOR = "soliq_inspector", "Inspektor"
    SOLIQ_ADMIN = "soliq_admin", "Soliq admin"


PORTAL_ROLES: dict[str, set[str]] = {
    Portal.STORE: {
        Role.ADMIN, Role.OMBORCHI, Role.BUXGALTER,
        Role.KASSIR, Role.AUDITOR, Role.FIRMA,
    },
    Portal.SUPPLIER: {
        Role.SUPPLIER_ADMIN, Role.SUPPLIER_SALES,
        Role.SUPPLIER_LOGISTICS, Role.SUPPLIER_BUXGALTER,
    },
    Portal.SOLIQ: {Role.SOLIQ_INSPECTOR, Role.SOLIQ_ADMIN},
}


class MembershipStatus(models.TextChoices):
    ACTIVE = "active", "Faol"
    BLOCKED = "blocked", "Bloklangan"
    PENDING = "pending", "Kutilmoqda"


class OtpPurpose(models.TextChoices):
    LOGIN = "login", "Login"
    REGISTER = "register", "Register"
    RESET = "reset", "Password reset"


class UserManager(BaseUserManager):
    def create_user(self, phone: str, full_name: str = "", **extra):
        if not phone:
            raise ValueError("Phone is required")
        user = self.model(phone=phone, full_name=full_name, **extra)
        # No usable password — phone-OTP is the auth path
        user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        user = self.model(phone=phone, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    """Phone-first user. Email is optional (for invoices/notifications)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=15, unique=True, db_index=True)
    full_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()
    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "accounts_user"

    def __str__(self) -> str:
        return self.full_name or self.phone


class Membership(TimeStamped):
    """User × Tenant join with role.

    `portal` discriminates which tenant table tenant_id points at — Store
    (chakana), SupplierCompany (distribyutor), or SoliqOffice. We avoid
    polymorphic FK because each portal evolves independently and DB-level
    referential integrity matters less than schema flexibility here.

    A single phone may hold memberships in multiple portals (a store
    admin who also runs a distribyutor side-business).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    portal = models.CharField(max_length=10, choices=Portal.choices, default=Portal.STORE)
    # tenant_id is the UUID of the portal-specific tenant row:
    #   portal=store    → tenants.Store.id
    #   portal=supplier → suppliers_portal.SupplierCompany.id
    #   portal=soliq    → tenants.SoliqOffice.id
    tenant_id = models.UUIDField(db_index=True)
    # Convenience FK for the store portal (the majority case). Nullable
    # because supplier/soliq members don't have a row here. Future-proof:
    # if SupplierCompany gets a real FK column too we can add it without
    # migrating existing data.
    store = models.ForeignKey(
        "tenants.Store",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="memberships",
    )
    role = models.CharField(max_length=30, choices=Role.choices)
    status = models.CharField(
        max_length=20, choices=MembershipStatus.choices, default=MembershipStatus.PENDING
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_membership"
        unique_together = (("user", "portal", "tenant_id"),)
        indexes = [
            models.Index(fields=("portal", "tenant_id", "status")),
            models.Index(fields=("user", "portal")),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(portal="store", store__isnull=False)
                    | ~models.Q(portal="store")
                ),
                name="membership_store_fk_when_store_portal",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.portal}:{self.tenant_id} ({self.role})"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        allowed = PORTAL_ROLES.get(self.portal, set())
        if self.role not in allowed:
            raise ValidationError(
                {"role": f"{self.role!r} {self.portal!r} portali uchun mos emas"}
            )


class OTPCode(TimeStamped):
    """
    SMS codes are stored hashed (never plaintext) so a DB dump doesn't leak
    them. Single use: consumed_at flips on success; expires_at caps the
    window. attempts caps brute force.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=15, db_index=True)
    code_hash = models.CharField(max_length=128)
    purpose = models.CharField(max_length=20, choices=OtpPurpose.choices)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    requester_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "accounts_otp_code"
        indexes = [models.Index(fields=("phone", "purpose", "consumed_at"))]

    def set_code(self, code: str) -> None:
        self.code_hash = make_password(code)

    def check_code(self, code: str) -> bool:
        return check_password(code, self.code_hash)

    @property
    def is_valid(self) -> bool:
        return self.consumed_at is None and timezone.now() < self.expires_at
