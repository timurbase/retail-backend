"""Auth + user-management views.

Anonymous endpoints (throttled):
  POST /api/auth/send-otp/         — request SMS code
  POST /api/auth/verify-otp/       — exchange code for token pair
  POST /api/auth/register/         — finish onboarding (store + admin membership)

Authenticated:
  POST /api/auth/select-store/     — re-mint token with active_store_id claim
  POST /api/auth/refresh/          — standard SimpleJWT
  POST /api/auth/logout/           — blacklist refresh
  GET  /api/auth/me/               — current user + memberships

Store-scoped (admin):
  GET  /api/users/                 — list teammates
  POST /api/users/invite/          — create user + membership(pending)
  PATCH /api/users/{id}/           — change role / profile
  DELETE /api/users/{id}/          — remove from store
  POST /api/users/{id}/toggle-status/
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import status, views, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.audit.recorder import record
from apps.core.permissions import IsAdmin
from apps.tenants.models import CompanyInfo, Store

from . import services
from .models import Membership, MembershipStatus, Portal, Role, User
from .serializers import (
    InviteUserSerializer,
    MembershipSerializer,
    RegisterStoreSerializer,
    SelectStoreSerializer,
    SelectSupplierSerializer,
    SendOtpSerializer,
    UpdateMembershipSerializer,
    UserListSerializer,
    UserSerializer,
    VerifyOtpSerializer,
    issue_token_pair,
)


def _client_ip(request) -> str | None:
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ---------- Anonymous auth ------------------------------------------------


class SendOtpView(views.APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "otp_send"

    def post(self, request):
        s = SendOtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            result = services.request_otp(
                s.validated_data["phone"],
                s.validated_data["purpose"],
                ip=_client_ip(request),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not result["ok"]:
            return Response(
                {"error": "Juda ko'p urinish. Bir soatdan keyin qayta urining."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return Response({"phone": result["phone"], "ttl": result["ttl"]})


class VerifyOtpView(views.APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "otp_verify"

    def post(self, request):
        s = VerifyOtpSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        try:
            result = services.verify_otp(
                s.validated_data["phone"],
                s.validated_data["code"],
                s.validated_data["purpose"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if result.user is None:
            messages = {
                "invalid": "Kod noto'g'ri yoki muddati o'tgan",
                "too_many_attempts": "Juda ko'p urinish. Yangi kod so'rang.",
                "no_user": "Bu telefon raqam ro'yxatdan o'tmagan. Avval ro'yxatdan o'ting.",
            }
            code = result.error or "invalid"
            return Response(
                {"error": messages.get(code, messages["invalid"]), "code": code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = result.user

        memberships = list(services.memberships_for(user))
        membership_payload = MembershipSerializer(memberships, many=True).data

        # Auto-select store if user only has one
        active_store_id = memberships[0].store_id if len(memberships) == 1 else None
        tokens = issue_token_pair(user, active_store_id=active_store_id)

        return Response(
            {
                **tokens,
                "user": UserSerializer(user).data,
                "memberships": membership_payload,
                "active_store_id": str(active_store_id) if active_store_id else None,
            }
        )


class RegisterStoreView(views.APIView):
    """Finalize register flow: caller is an authenticated User with no
    memberships (after verify-otp purpose=register). We create the Store +
    CompanyInfo + admin Membership atomically.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        s = RegisterStoreSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        user: User = request.user
        if Membership.objects.filter(user=user).exists():
            return Response(
                {"error": "Foydalanuvchi allaqachon do'konga biriktirilgan"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                if not user.full_name and s.validated_data.get("full_name"):
                    user.full_name = s.validated_data["full_name"]
                    user.save(update_fields=("full_name",))

                store = Store.objects.create(name=s.validated_data["company_name"])
                CompanyInfo.objects.create(
                    store=store,
                    stir=s.validated_data["stir"],
                    stir_verified=False,
                    name=s.validated_data["company_name"],
                    activity=s.validated_data.get("activity", ""),
                    director=s.validated_data.get("director", ""),
                    address=s.validated_data.get("address", ""),
                    phone=user.phone,
                    email=user.email,
                )
                membership = Membership.objects.create(
                    user=user,
                    portal=Portal.STORE,
                    tenant_id=store.id,
                    store=store,
                    role=Role.ADMIN,
                    status=MembershipStatus.ACTIVE,
                )
        except IntegrityError:
            return Response(
                {
                    "error": "Bu STIR allaqachon ro'yxatdan o'tgan",
                    "code": "stir_taken",
                },
                status=status.HTTP_409_CONFLICT,
            )

        tokens = issue_token_pair(user, active_store_id=store.id)

        record(
            request,
            actor=user,
            store_id=store.id,
            action="create",
            object_type="company",
            object_id=str(store.id),
            object_label=store.name,
            details="Yangi do'kon ro'yxatdan o'tdi",
        )

        return Response(
            {
                **tokens,
                "user": UserSerializer(user).data,
                "memberships": MembershipSerializer([membership], many=True).data,
                "active_store_id": str(store.id),
            },
            status=status.HTTP_201_CREATED,
        )


# ---------- Authenticated --------------------------------------------------


class SelectStoreView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        s = SelectStoreSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        store_id = s.validated_data["store_id"]

        membership = (
            Membership.objects.filter(
                user=request.user, store_id=store_id, status=MembershipStatus.ACTIVE
            )
            .select_related("store")
            .first()
        )
        if membership is None:
            return Response(
                {"error": "Bu do'konga kira olmaysiz"},
                status=status.HTTP_403_FORBIDDEN,
            )

        services.update_membership_last_seen(request.user, store_id)
        tokens = issue_token_pair(request.user, active_store_id=store_id)
        return Response(
            {
                **tokens,
                "active_store_id": str(store_id),
                "role": membership.role,
            }
        )


class SelectSupplierView(views.APIView):
    """Mirror of SelectStoreView but for the distribyutor portal.

    Issues a fresh token with active_portal='supplier' + the supplier's
    tenant_id, after verifying the user holds an active supplier membership.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        s = SelectSupplierSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        supplier_id = s.validated_data["supplier_id"]

        membership = (
            Membership.objects.filter(
                user=request.user,
                portal=Portal.SUPPLIER,
                tenant_id=supplier_id,
                status=MembershipStatus.ACTIVE,
            )
            .only("id", "role")
            .first()
        )
        if membership is None:
            return Response(
                {"error": "Bu distribyutorga kira olmaysiz"},
                status=status.HTTP_403_FORBIDDEN,
            )

        tokens = issue_token_pair(
            request.user,
            active_tenant_id=supplier_id,
            active_portal="supplier",
        )
        return Response(
            {
                **tokens,
                "active_tenant_id": str(supplier_id),
                "active_portal": "supplier",
                "role": membership.role,
            }
        )


class MeView(views.APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        memberships = list(services.memberships_for(request.user))
        return Response(
            {
                "user": UserSerializer(request.user).data,
                "memberships": MembershipSerializer(memberships, many=True).data,
                "active_store_id": getattr(request, "active_store_id", None),
            }
        )


# ---------- Store-scoped: team management ---------------------------------


class TeamViewSet(viewsets.ViewSet):
    """
    /api/users/                  GET  list
    /api/users/invite/           POST invite by phone
    /api/users/{id}/             PATCH role / profile
    /api/users/{id}/             DELETE remove from store
    /api/users/{id}/toggle-status/  POST flip active/blocked
    """

    permission_classes = (IsAdmin,)

    def _store_qs(self, request) -> list[User]:
        # Subquery: pull this user's membership in the active store
        memberships = Membership.objects.filter(
            user=OuterRef("pk"), store_id=request.active_store_id
        )
        return (
            User.objects.filter(memberships__store_id=request.active_store_id)
            .distinct()
            .annotate(
                role=Subquery(memberships.values("role")[:1]),
                status=Subquery(memberships.values("status")[:1]),
                membership_id=Subquery(memberships.values("id")[:1]),
            )
            .order_by("-created_at")
        )

    def list(self, request):
        qs = self._store_qs(request)
        return Response(UserListSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"])
    def invite(self, request):
        s = InviteUserSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            phone = services._normalize_phone(s.validated_data["phone"])
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "full_name": s.validated_data.get("full_name", ""),
                    "email": s.validated_data.get("email", ""),
                },
            )
            membership, m_created = Membership.objects.get_or_create(
                user=user,
                portal=Portal.STORE,
                tenant_id=request.active_store_id,
                defaults={
                    "store_id": request.active_store_id,
                    "role": s.validated_data["role"],
                    "status": MembershipStatus.PENDING,
                },
            )
            if not m_created:
                return Response(
                    {"error": "Foydalanuvchi allaqachon biriktirilgan"},
                    status=status.HTTP_409_CONFLICT,
                )

        record(
            request,
            action="create",
            object_type="user",
            object_id=str(user.id),
            object_label=user.full_name or user.phone,
            details=f"Yangi foydalanuvchi taklif qilindi · rol: {s.validated_data['role']}",
        )
        return Response(
            MembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )

    def partial_update(self, request, pk=None):
        membership = get_object_or_404(
            Membership, user_id=pk, store_id=request.active_store_id
        )
        s = UpdateMembershipSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        changes: list[str] = []
        if "role" in data and data["role"] != membership.role:
            changes.append(f"role: {membership.role} → {data['role']}")
            membership.role = data["role"]
        if "status" in data and data["status"] != membership.status:
            changes.append(f"status: {membership.status} → {data['status']}")
            membership.status = data["status"]
        membership.save()

        user = membership.user
        if "full_name" in data or "email" in data:
            if "full_name" in data:
                changes.append(f"full_name: {user.full_name} → {data['full_name']}")
                user.full_name = data["full_name"]
            if "email" in data:
                changes.append(f"email: {user.email} → {data['email']}")
                user.email = data["email"]
            user.save()

        record(
            request,
            action="update",
            object_type="user",
            object_id=str(user.id),
            object_label=user.full_name or user.phone,
            details="; ".join(changes) or "tahrirlandi",
        )
        return Response(MembershipSerializer(membership).data)

    def destroy(self, request, pk=None):
        membership = get_object_or_404(
            Membership, user_id=pk, store_id=request.active_store_id
        )
        if membership.user_id == request.user.id:
            return Response(
                {"error": "O'zingizni o'chira olmaysiz"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        label = membership.user.full_name or membership.user.phone
        membership.delete()
        record(
            request,
            action="delete",
            object_type="user",
            object_id=str(pk),
            object_label=label,
            details="Foydalanuvchi do'kondan o'chirildi",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="toggle-status")
    def toggle_status(self, request, pk=None):
        membership = get_object_or_404(
            Membership, user_id=pk, store_id=request.active_store_id
        )
        membership.status = (
            MembershipStatus.BLOCKED
            if membership.status == MembershipStatus.ACTIVE
            else MembershipStatus.ACTIVE
        )
        membership.save(update_fields=("status",))
        record(
            request,
            action="update",
            object_type="user",
            object_id=str(membership.user_id),
            object_label=membership.user.full_name or membership.user.phone,
            details=f"Status: {membership.status}",
        )
        return Response(MembershipSerializer(membership).data)
