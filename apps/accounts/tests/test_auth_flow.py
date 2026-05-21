"""
End-to-end happy-path: register a new store via phone-OTP, then read
and update company info, then list audit log.

Reads OTP straight out of OTPCode rows (DB) instead of intercepting SMS.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, OTPCode, User
from apps.audit.models import AuditEntry
from apps.tenants.models import CompanyInfo


@pytest.fixture
def client() -> APIClient:
    c = APIClient()
    # Disable throttles in tests so repeated runs don't 429
    c.handler.enforce_csrf_checks = False
    return c


def _latest_code(phone: str, purpose: str) -> str:
    otp = (
        OTPCode.objects.filter(phone=phone, purpose=purpose, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    assert otp is not None, "expected an open OTP row"
    # We can't pull plaintext (hashed), so write it manually for the test:
    # use the in-memory code by re-issuing with a known seed.
    raise RuntimeError("OTP plaintext not available — use _send_with_known_code()")


def _send_with_known_code(monkeypatch, phone: str, code: str = "123456"):
    """Override the random generator so tests can assert the exact code."""
    from apps.accounts import services

    monkeypatch.setattr(services, "_generate_code", lambda: code)


@pytest.mark.django_db
def test_happy_path_register_then_company_crud(client: APIClient, monkeypatch, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    _send_with_known_code(monkeypatch, "+998901112233", code="654321")

    # 1. send-otp register
    r = client.post(
        "/api/auth/send-otp/",
        {"phone": "901112233", "purpose": "register"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["phone"] == "+998901112233"

    # 2. verify-otp
    r = client.post(
        "/api/auth/verify-otp/",
        {"phone": "901112233", "code": "654321", "purpose": "register"},
        format="json",
    )
    assert r.status_code == 200, r.content
    access = r.data["access"]
    assert r.data["user"]["phone"] == "+998901112233"
    assert r.data["memberships"] == []
    assert User.objects.filter(phone="+998901112233").exists()

    # 3. register-store
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r = client.post(
        "/api/auth/register/",
        {
            "stir": "301234567",
            "company_name": "Test MChJ",
            "full_name": "Test User",
            "director": "Test Director",
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    access = r.data["access"]
    store_id = r.data["active_store_id"]
    assert Membership.objects.filter(user__phone="+998901112233", role="admin").exists()
    assert CompanyInfo.objects.filter(store_id=store_id, name="Test MChJ").exists()

    # 4. /api/company/ GET (with new token that carries active_store_id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r = client.get("/api/company/")
    assert r.status_code == 200, r.content
    assert r.data["name"] == "Test MChJ"
    assert r.data["stir"] == "301234567"

    # 5. PATCH
    r = client.patch(
        "/api/company/",
        {"director": "New Director", "email": "boss@example.uz"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["director"] == "New Director"

    # 6. Audit trail recorded the company update + the company create at registration
    r = client.get("/api/audit-log/")
    assert r.status_code == 200, r.content
    rows = r.data["results"]
    assert any(
        e["action"] == "update" and e["object_type"] == "company" for e in rows
    ), rows
    assert any(
        e["action"] == "create" and e["object_type"] == "company" for e in rows
    ), rows

    # 7. Audit table is append-only at the ORM layer (ValueError on .delete())
    entry = AuditEntry.objects.first()
    with pytest.raises(NotImplementedError):
        entry.delete()


@pytest.mark.django_db
def test_otp_wrong_code_rejects(client: APIClient, monkeypatch, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    _send_with_known_code(monkeypatch, "+998901112244", code="111111")
    client.post(
        "/api/auth/send-otp/",
        {"phone": "901112244", "purpose": "login"},
        format="json",
    )
    r = client.post(
        "/api/auth/verify-otp/",
        {"phone": "901112244", "code": "999999", "purpose": "login"},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_login_on_unregistered_phone_is_refused(
    client: APIClient, monkeypatch, settings
):
    """Security: verify-otp purpose=login MUST NOT auto-create a user."""
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    _send_with_known_code(monkeypatch, "+998905554433", code="222222")

    client.post(
        "/api/auth/send-otp/",
        {"phone": "905554433", "purpose": "login"},
        format="json",
    )
    r = client.post(
        "/api/auth/verify-otp/",
        {"phone": "905554433", "code": "222222", "purpose": "login"},
        format="json",
    )
    assert r.status_code == 400, r.content
    assert r.data["code"] == "no_user"
    # And no user was silently materialised
    from apps.accounts.models import User as U

    assert not U.objects.filter(phone="+998905554433").exists()


@pytest.mark.django_db
def test_register_stir_validation(client: APIClient, monkeypatch, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    _send_with_known_code(monkeypatch, "+998905554466", code="333333")
    client.post(
        "/api/auth/send-otp/",
        {"phone": "905554466", "purpose": "register"},
        format="json",
    )
    r = client.post(
        "/api/auth/verify-otp/",
        {"phone": "905554466", "code": "333333", "purpose": "register"},
        format="json",
    )
    access = r.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    # 8-digit STIR — should be rejected
    r = client.post(
        "/api/auth/register/",
        {"stir": "12345678", "company_name": "X", "full_name": "Y"},
        format="json",
    )
    assert r.status_code == 400, r.content
    assert "stir" in r.data


@pytest.mark.django_db
def test_register_duplicate_stir_returns_409(
    client: APIClient, monkeypatch, settings
):
    from apps.tenants.models import CompanyInfo, Store

    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    # Pre-existing store with STIR 301234567
    store = Store.objects.create(name="Existing")
    CompanyInfo.objects.create(store=store, stir="301234567", name="Existing")

    _send_with_known_code(monkeypatch, "+998905554477", code="444444")
    client.post(
        "/api/auth/send-otp/",
        {"phone": "905554477", "purpose": "register"},
        format="json",
    )
    r = client.post(
        "/api/auth/verify-otp/",
        {"phone": "905554477", "code": "444444", "purpose": "register"},
        format="json",
    )
    access = r.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    r = client.post(
        "/api/auth/register/",
        {"stir": "301234567", "company_name": "Dup", "full_name": "Y"},
        format="json",
    )
    assert r.status_code == 409, r.content
    assert r.data["code"] == "stir_taken"


@pytest.mark.django_db
def test_company_patch_requires_admin(client: APIClient, monkeypatch, settings):
    """Buxgalter membership should be 403 on PATCH /api/company/."""
    from apps.accounts.models import Membership, MembershipStatus, Role
    from apps.tenants.models import CompanyInfo, Store

    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }

    store = Store.objects.create(name="X")
    CompanyInfo.objects.create(store=store, stir="123456789", name="X")
    user = User.objects.create_user(phone="+998901112266", full_name="Bux")
    Membership.objects.create(
        user=user,
        portal="store",
        tenant_id=store.id,
        store=store,
        role=Role.BUXGALTER,
        status=MembershipStatus.ACTIVE,
    )

    from apps.accounts.serializers import issue_token_pair

    access = issue_token_pair(user, active_store_id=store.id)["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    r = client.get("/api/company/")
    assert r.status_code == 200

    r = client.patch("/api/company/", {"name": "Hacked"}, format="json")
    assert r.status_code == 403
