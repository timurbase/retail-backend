"""Happy-path retail document flow: create manual → approve → stats."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipStatus, Role, User
from apps.accounts.serializers import issue_token_pair
from apps.documents.models import (
    DocumentStatus,
    ProductRow,
    ProductRowStatus,
    RetailDocument,
)
from apps.products.models import Product, StockMovement
from apps.suppliers.models import Supplier
from apps.tenants.models import Store


@pytest.fixture
def admin_client(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    store = Store.objects.create(name="Test Store")
    user = User.objects.create_user(phone="+998901111300", full_name="Admin")
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
    supplier = Supplier.objects.create(
        store=store, name="Alpha", stir="301234567", verified=True
    )
    return client, store, user, supplier


@pytest.mark.django_db
def test_create_manual_then_approve_posts_stock(admin_client):
    client, store, _, supplier = admin_client
    # Pre-existing product to be hit by doc_approve
    product = Product.objects.create(
        store=store, name="Mol go'shti", mxik="0201301000",
        unit="kg", current_stock=Decimal("0"), min_stock=Decimal("5"),
        avg_price=Decimal("85000"),
    )

    r = client.post(
        "/api/documents/manual/",
        {
            "supplier_id": str(supplier.id),
            "number": "12345",
            "date": "2026-05-21",
            "rows": [
                {
                    "rawName": "Mol go'shti birinchi nav",
                    "mxik": "0201301000",
                    "unit": "kg",
                    "quantity": "15.000",
                    "price": "85000.00",
                    "mappedProductId": str(product.id),
                },
                {
                    "rawName": "Coca-Cola 0.5L",
                    "mxik": "",
                    "unit": "dona",
                    "quantity": "50.000",
                    "price": "7500.00",
                },
            ],
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    doc_id = r.data["id"]
    assert r.data["status"] == DocumentStatus.REVIEW
    assert len(r.data["rows"]) == 2
    # 15 * 85000 + 50 * 7500 = 1275000 + 375000 = 1650000
    assert Decimal(r.data["total_amount"]) == Decimal("1650000.00")

    # Detail
    r = client.get(f"/api/documents/{doc_id}/")
    assert r.status_code == 200, r.content
    assert len(r.data["rows"]) == 2

    # Approve
    r = client.post(f"/api/documents/{doc_id}/approve/")
    assert r.status_code == 200, r.content
    assert r.data["status"] == DocumentStatus.APPROVED

    # Product current_stock bumped by the mapped row
    product.refresh_from_db()
    assert product.current_stock == Decimal("15.000")
    assert product.last_received_at is not None
    assert StockMovement.objects.filter(
        product=product, kind="doc_approve", document_id=doc_id
    ).exists()


@pytest.mark.django_db
def test_reject_document(admin_client):
    client, store, _, supplier = admin_client
    doc = RetailDocument.objects.create(
        store=store, number="X1", source="manual", supplier=supplier,
        date="2026-05-21", status=DocumentStatus.REVIEW,
    )
    r = client.post(
        f"/api/documents/{doc.id}/reject/",
        {"reason": "Duplikat"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["status"] == DocumentStatus.REJECTED


@pytest.mark.django_db
def test_row_actions_and_recalc(admin_client):
    client, store, _, supplier = admin_client
    doc = RetailDocument.objects.create(
        store=store, number="X2", source="manual", supplier=supplier,
        date="2026-05-21", status=DocumentStatus.REVIEW,
    )
    row = ProductRow.objects.create(
        document=doc,
        raw_name="Choy 100g",
        mxik_code="0902200000",
        mxik_name="Qora choy",
        mxik_confidence=0.43,
        alternatives=[
            {"code": "0902409000", "name": "Choy yaproq", "confidence": 0.41},
            {"code": "0902100000", "name": "Yashil choy", "confidence": 0.38},
        ],
        unit="dona", quantity=Decimal("20"), price=Decimal("12000"),
        total=Decimal("240000"), status=ProductRowStatus.AMBIGUOUS,
        order_index=0,
    )
    doc.review_count = 1
    doc.save()

    # PATCH MXIK → confidence 0.95 → matched
    r = client.patch(
        f"/api/documents/{doc.id}/rows/{row.id}/mxik/",
        {"code": "0902200000", "name": "Qora choy, qadoqlangan", "confidence": 0.95},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["status"] == ProductRowStatus.MATCHED
    doc.refresh_from_db()
    assert doc.review_count == 0

    # Approve row
    r = client.post(f"/api/documents/{doc.id}/rows/{row.id}/approve/")
    assert r.status_code == 200
    assert r.data["status"] == ProductRowStatus.APPROVED


@pytest.mark.django_db
def test_select_variant(admin_client):
    client, store, _, supplier = admin_client
    doc = RetailDocument.objects.create(
        store=store, number="X3", source="manual", supplier=supplier,
        date="2026-05-21", status=DocumentStatus.REVIEW,
    )
    row = ProductRow.objects.create(
        document=doc, raw_name="Choy", mxik_code="0902200000",
        mxik_name="Qora choy", mxik_confidence=0.4,
        alternatives=[
            {"code": "0902100000", "name": "Yashil choy", "confidence": 0.85},
        ],
        unit="dona", quantity=Decimal("1"), price=Decimal("1"),
        total=Decimal("1"), status=ProductRowStatus.AMBIGUOUS,
    )
    r = client.post(
        f"/api/documents/{doc.id}/rows/{row.id}/select-variant/",
        {"code": "0902100000"},
        format="json",
    )
    assert r.status_code == 200, r.content
    row.refresh_from_db()
    assert row.mxik_code == "0902100000"
    assert row.status == ProductRowStatus.APPROVED


@pytest.mark.django_db
def test_bulk_approve_high_confidence(admin_client):
    client, store, _, supplier = admin_client
    doc = RetailDocument.objects.create(
        store=store, number="X4", source="manual", supplier=supplier,
        date="2026-05-21", status=DocumentStatus.REVIEW,
    )
    for i in range(3):
        ProductRow.objects.create(
            document=doc, raw_name=f"R{i}", mxik_confidence=0.95,
            unit="dona", quantity=Decimal("1"), price=Decimal("1"),
            total=Decimal("1"), status=ProductRowStatus.MATCHED, order_index=i,
        )
    ProductRow.objects.create(
        document=doc, raw_name="Low", mxik_confidence=0.5,
        unit="dona", quantity=Decimal("1"), price=Decimal("1"),
        total=Decimal("1"), status=ProductRowStatus.NEW, order_index=3,
    )
    r = client.post(f"/api/documents/{doc.id}/bulk-approve-high-confidence/")
    assert r.status_code == 200, r.content
    assert r.data["count"] == 3


@pytest.mark.django_db
def test_document_stats(admin_client):
    client, store, _, supplier = admin_client
    doc = RetailDocument.objects.create(
        store=store, number="S1", source="manual", supplier=supplier,
        date="2026-05-21", status=DocumentStatus.REVIEW, review_count=2,
    )
    ProductRow.objects.create(
        document=doc, raw_name="A", unit="dona",
        quantity=Decimal("1"), price=Decimal("1"), total=Decimal("1"),
        status=ProductRowStatus.MATCHED,
    )
    ProductRow.objects.create(
        document=doc, raw_name="B", unit="dona",
        quantity=Decimal("1"), price=Decimal("1"), total=Decimal("1"),
        status=ProductRowStatus.NEW,
    )
    r = client.get("/api/documents/stats/")
    assert r.status_code == 200, r.content
    assert r.data["totalRows"] == 2
    assert r.data["approvedRows"] == 1
    assert r.data["reviewQueue"] == 2
