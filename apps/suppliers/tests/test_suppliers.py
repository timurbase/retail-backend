"""Happy-path supplier CRUD + Soliq.uz mock lookup."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipStatus, Role, User
from apps.accounts.serializers import issue_token_pair
from apps.suppliers.models import Supplier
from apps.tenants.models import Store


@pytest.fixture
def admin_client(settings) -> tuple[APIClient, Store, User]:
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    store = Store.objects.create(name="Test Store")
    user = User.objects.create_user(phone="+998901111100", full_name="Admin")
    Membership.objects.create(
        user=user,
        portal="store",
        tenant_id=store.id,
        store=store,
        role=Role.ADMIN,
        status=MembershipStatus.ACTIVE,
    )
    access = issue_token_pair(user, active_store_id=store.id)["access"]
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client, store, user


@pytest.mark.django_db
def test_create_list_supplier(admin_client):
    client, store, _ = admin_client
    r = client.post(
        "/api/suppliers/",
        {"name": "Alpha Distribution OOO", "stir": "301234567", "verified": True},
        format="json",
    )
    assert r.status_code == 201, r.content
    sup_id = r.data["id"]
    assert r.data["stir"] == "301234567"
    assert Supplier.objects.filter(store=store, stir="301234567").exists()

    # List filtered by verified
    r = client.get("/api/suppliers/?verified=true")
    assert r.status_code == 200, r.content
    assert any(s["id"] == sup_id for s in r.data["results"])

    # Search by stir
    r = client.get("/api/suppliers/?search=3012")
    assert r.status_code == 200
    assert len(r.data["results"]) >= 1


@pytest.mark.django_db
def test_lookup_stir_mock(admin_client):
    client, _, _ = admin_client
    r = client.get("/api/suppliers/lookup-stir/?stir=301234567")
    assert r.status_code == 200, r.content
    assert r.data["verified"] is True
    assert "OOO" in r.data["name"] or "MChJ" in r.data["name"]

    r = client.get("/api/suppliers/lookup-stir/?stir=401234567")
    assert r.status_code == 404


@pytest.mark.django_db
def test_invalid_stir_rejected(admin_client):
    client, _, _ = admin_client
    r = client.post(
        "/api/suppliers/",
        {"name": "Bad", "stir": "12345"},  # only 5 digits
        format="json",
    )
    assert r.status_code == 400
    assert "stir" in r.data


@pytest.mark.django_db
def test_duplicate_stir_within_store_rejected(admin_client):
    client, store, _ = admin_client
    Supplier.objects.create(store=store, name="Existing", stir="301234567")
    r = client.post(
        "/api/suppliers/",
        {"name": "Dup", "stir": "301234567"},
        format="json",
    )
    assert r.status_code == 400, r.content
    assert "stir" in r.data


@pytest.mark.django_db
def test_delete_writes_audit(admin_client):
    from apps.audit.models import AuditEntry

    client, store, _ = admin_client
    sup = Supplier.objects.create(store=store, name="Tmp", stir="302345678")
    r = client.delete(f"/api/suppliers/{sup.id}/")
    assert r.status_code == 204
    assert AuditEntry.objects.filter(
        object_type="supplier", action="delete", object_id=str(sup.id)
    ).exists()
