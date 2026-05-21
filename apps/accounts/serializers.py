"""Auth + user serializers."""

from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.validators import normalize_stir

from .models import Membership, MembershipStatus, Role, User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "phone", "full_name", "email", "last_login", "created_at")
        read_only_fields = ("id", "phone", "last_login", "created_at")


class MembershipSerializer(serializers.ModelSerializer):
    store_id = serializers.UUIDField(source="store.id", read_only=True, default=None)
    store_name = serializers.CharField(source="store.name", read_only=True, default=None)
    tenant_name = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = (
            "id",
            "portal",
            "tenant_id",
            "tenant_name",
            "store_id",
            "store_name",
            "role",
            "status",
            "last_seen_at",
            "created_at",
        )
        read_only_fields = (
            "id", "portal", "tenant_id", "tenant_name",
            "store_id", "store_name", "last_seen_at", "created_at",
        )

    def get_tenant_name(self, obj):
        if obj.store_id:
            return obj.store.name
        # supplier / soliq tenants: resolved on read to avoid an extra join
        if obj.portal == "supplier":
            try:
                from apps.supplier_portal.models import SupplierCompany
                t = SupplierCompany.objects.filter(id=obj.tenant_id).only("name").first()
                return t.name if t else None
            except Exception:
                return None
        if obj.portal == "soliq":
            from apps.tenants.models import SoliqOffice
            t = SoliqOffice.objects.filter(id=obj.tenant_id).only("name").first()
            return t.name if t else None
        return None


class UserListSerializer(serializers.ModelSerializer):
    """Used by /api/users/ to mirror the frontend User type
    (lib/types.ts → User) by joining membership info onto the user row.

    The viewset annotates `role`, `status`, `membership_id` via subqueries.
    """

    role = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    membership_id = serializers.UUIDField(read_only=True)
    last_login_at = serializers.DateTimeField(source="last_login", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "membership_id",
            "phone",
            "full_name",
            "email",
            "role",
            "status",
            "last_login_at",
            "created_at",
        )
        read_only_fields = fields


class SendOtpSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    purpose = serializers.ChoiceField(choices=["login", "register", "reset"])


class VerifyOtpSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(min_length=4, max_length=8)
    purpose = serializers.ChoiceField(choices=["login", "register", "reset"])


class SelectStoreSerializer(serializers.Serializer):
    store_id = serializers.UUIDField()


class SelectSupplierSerializer(serializers.Serializer):
    supplier_id = serializers.UUIDField()


class RegisterStoreSerializer(serializers.Serializer):
    """Used after successful register-OTP to create the Store + first admin Membership."""

    stir = serializers.CharField(max_length=14, min_length=9)
    company_name = serializers.CharField(max_length=200)
    activity = serializers.CharField(max_length=200, required=False, allow_blank=True)
    director = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=200)

    def validate_stir(self, value: str) -> str:
        try:
            return normalize_stir(value)
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc


class InviteUserSerializer(serializers.Serializer):
    """Admin invites a teammate by phone."""

    phone = serializers.CharField(max_length=20)
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=Role.choices)


class UpdateMembershipSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    status = serializers.ChoiceField(choices=MembershipStatus.choices, required=False)
    full_name = serializers.CharField(max_length=200, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)


# --- Token helpers ---------------------------------------------------------


def issue_token_pair(
    user: User,
    active_store_id=None,
    active_tenant_id=None,
    active_portal: str | None = None,
) -> dict:
    """Mint a refresh+access pair with the active tenant claim baked in.

    Two compatible call shapes:
      - issue_token_pair(user, active_store_id=<uuid>)
            → embeds active_store_id (legacy) AND active_tenant_id=<uuid>
              with active_portal="store" so new clients can rely on the
              portal-agnostic claim.
      - issue_token_pair(user, active_tenant_id=<uuid>, active_portal="supplier")
            → portal-specific tenant context.
    """
    refresh = RefreshToken.for_user(user)
    # Backwards-compat: legacy callers pass active_store_id.
    if active_store_id is not None and active_tenant_id is None:
        active_tenant_id = active_store_id
        active_portal = active_portal or "store"

    if active_store_id is not None:
        refresh["active_store_id"] = str(active_store_id)
        refresh.access_token["active_store_id"] = str(active_store_id)
    if active_tenant_id is not None:
        refresh["active_tenant_id"] = str(active_tenant_id)
        refresh.access_token["active_tenant_id"] = str(active_tenant_id)
    if active_portal:
        refresh["active_portal"] = active_portal
        refresh.access_token["active_portal"] = active_portal
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


class PhoneOtpTokenSerializer(serializers.Serializer):
    """Required by SIMPLE_JWT['TOKEN_OBTAIN_SERIALIZER'] but unused in
    practice — we mint tokens directly via verify-otp/. Keeping a stub
    here keeps default JWT plumbing happy."""

    def validate(self, attrs):
        raise serializers.ValidationError(
            "Use /api/auth/verify-otp/ to obtain tokens"
        )
