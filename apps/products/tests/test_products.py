"""Happy-path product catalog + stock-adjust + MXIK typeahead."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipStatus, Role, User
from apps.accounts.serializers import issue_token_pair
from apps.products.models import Product, StockMovement
from apps.tenants.models import Store


@pytest.fixture
def admin_client(settings) -> tuple[APIClient, Store, User]:
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    store = Store.objects.create(name="Test Store")
    user = User.objects.create_user(phone="+998901111200", full_name="Admin")
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
def test_product_crud_and_stats(admin_client):
    client, store, _ = admin_client
    # Create
    r = client.post(
        "/api/products/",
        {
            "name": "Mol go'shti",
            "mxik": "0201301000",
            "unit": "kg",
            "current_stock": "15.000",
            "min_stock": "10.000",
            "avg_price": "85000.00",
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    pid = r.data["id"]

    # Another product, critical stock
    r = client.post(
        "/api/products/",
        {
            "name": "Coca",
            "mxik": "",
            "unit": "dona",
            "current_stock": "3.000",
            "min_stock": "20.000",
            "avg_price": "7500.00",
        },
        format="json",
    )
    assert r.status_code == 201, r.content

    # Stats
    r = client.get("/api/products/stats/")
    assert r.status_code == 200, r.content
    assert r.data["total"] == 2
    assert r.data["critical"] == 1
    assert r.data["withMxik"] == 1
    assert r.data["withoutMxik"] == 1

    # List filter low_stock
    r = client.get("/api/products/?low_stock=true")
    assert r.status_code == 200
    assert len(r.data["results"]) == 1
    assert r.data["results"][0]["name"] == "Coca"

    # PATCH
    r = client.patch(f"/api/products/{pid}/", {"min_stock": "20.000"}, format="json")
    assert r.status_code == 200
    assert r.data["min_stock"] == "20.000"


@pytest.mark.django_db
def test_stock_adjust_writes_movement(admin_client):
    client, store, _ = admin_client
    p = Product.objects.create(
        store=store, name="Sut", mxik="0401200000", unit="dona",
        current_stock=Decimal("10"), min_stock=Decimal("5"), avg_price=Decimal("8500"),
    )

    # Kirim 5 → 15
    r = client.post(
        f"/api/products/{p.id}/stock-adjust/",
        {"kind": "kirim", "qty": "5.000", "reason": "Test"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["current_stock"] == "15.000"
    assert r.data["last_received_at"] is not None
    assert StockMovement.objects.filter(product=p, kind="kirim").exists()

    # Chiqim 3 → 12
    r = client.post(
        f"/api/products/{p.id}/stock-adjust/",
        {"kind": "chiqim", "qty": "3.000"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["current_stock"] == "12.000"

    # Inventarizatsiya 100 → 100
    r = client.post(
        f"/api/products/{p.id}/stock-adjust/",
        {"kind": "inventarizatsiya", "qty": "100.000"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["current_stock"] == "100.000"

    # Over-draw refused
    r = client.post(
        f"/api/products/{p.id}/stock-adjust/",
        {"kind": "chiqim", "qty": "9999.000"},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_mxik_typeahead(admin_client):
    client, _, _ = admin_client
    r = client.get("/api/mxik/?q=mol")
    assert r.status_code == 200, r.content
    assert len(r.data) >= 1
    codes = [item["code"] for item in r.data]
    assert "0201301000" in codes

    r = client.get("/api/mxik/?q=&limit=5")
    assert r.status_code == 200
    assert r.data == []
