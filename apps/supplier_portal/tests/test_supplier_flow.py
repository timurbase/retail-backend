"""
Supplier portal integration tests.

Happy paths covered:
  - Login as supplier_admin → list stores
  - Create invoice → mark-paid → verify PaymentRecord created
  - Reject incoming order with reason
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipStatus, Portal, Role, User
from apps.accounts.serializers import issue_token_pair
from apps.supplier_portal.models import (
    IncomingOrder,
    IncomingOrderItem,
    IncomingOrderStatus,
    OutgoingInvoice,
    OutgoingInvoiceStatus,
    PaymentRecord,
    PaymentStatus,
    SupplierCompany,
    SupplierProduct,
    SupplierStore,
)


@pytest.fixture
def settings_no_throttle(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
    }
    return settings


@pytest.fixture
def supplier_setup(db):
    """Create a SupplierCompany + admin user + active membership + sample store."""
    company = SupplierCompany.objects.create(
        name="Alpha Distribution OOO",
        stir="301234567",
        director="A. Alimov",
        phone="+998901234567",
        region="Toshkent",
    )
    user = User.objects.create_user(phone="+998901112233", full_name="Sup Admin")
    Membership.objects.create(
        user=user,
        portal=Portal.SUPPLIER,
        tenant_id=company.id,
        role=Role.SUPPLIER_ADMIN,
        status=MembershipStatus.ACTIVE,
    )
    store = SupplierStore.objects.create(
        supplier=company,
        name="Lazzat Shop",
        stir="305555555",
        region="Toshkent",
        district="Yunusobod",
        reliability_score=Decimal("8.5"),
        monthly_volume=Decimal("12000000"),
    )
    return {"company": company, "user": user, "store": store}


@pytest.fixture
def auth_client(supplier_setup):
    client = APIClient()
    tokens = issue_token_pair(
        supplier_setup["user"],
        active_tenant_id=supplier_setup["company"].id,
        active_portal="supplier",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client


@pytest.mark.django_db
def test_supplier_admin_lists_stores(auth_client, supplier_setup, settings_no_throttle):
    r = auth_client.get("/api/supplier/stores/")
    assert r.status_code == 200, r.content
    results = r.data["results"] if isinstance(r.data, dict) else r.data
    names = [s["name"] for s in results]
    assert supplier_setup["store"].name in names


@pytest.mark.django_db
def test_company_singleton_get_and_patch(auth_client, supplier_setup, settings_no_throttle):
    r = auth_client.get("/api/supplier/company/")
    assert r.status_code == 200, r.content
    assert r.data["name"] == supplier_setup["company"].name

    r = auth_client.patch(
        "/api/supplier/company/",
        {"director": "B. Beruniy"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["director"] == "B. Beruniy"


@pytest.mark.django_db
def test_create_invoice_then_mark_paid_creates_payment(
    auth_client, supplier_setup, settings_no_throttle
):
    company = supplier_setup["company"]
    store = supplier_setup["store"]

    SupplierProduct.objects.create(
        supplier=company,
        name="Coca-Cola 1L",
        unit="dona",
        base_price=Decimal("12000.00"),
    )

    payload = {
        "store_id": str(store.id),
        "items": [
            {
                "name": "Coca-Cola 1L",
                "mxik": "1234567890",
                "unit": "dona",
                "quantity": "10",
                "price": "12000.00",
            },
            {
                "name": "Fanta 1L",
                "unit": "dona",
                "quantity": "5",
                "price": "11000.00",
            },
        ],
        "due_date": "2026-06-01",
        "tracking_note": "Yetkazib berish — ertaga",
    }
    r = auth_client.post("/api/supplier/invoices/", payload, format="json")
    assert r.status_code == 201, r.content
    invoice_id = r.data["id"]
    assert r.data["status"] == "draft"
    assert r.data["number"].startswith("ALP-")
    # 10*12000 + 5*11000 = 175000
    assert Decimal(r.data["total_amount"]) == Decimal("175000.00")
    assert len(r.data["items"]) == 2

    # mark-paid
    r = auth_client.post(
        f"/api/supplier/invoices/{invoice_id}/mark-paid/",
        {"method": "click"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["status"] == "paid"
    assert r.data["paid_at"] is not None

    payment = PaymentRecord.objects.get(invoice_id=invoice_id)
    assert payment.status == PaymentStatus.PAID
    assert payment.method == "click"
    assert payment.paid_amount == Decimal("175000.00")
    assert payment.store_name == store.name


@pytest.mark.django_db
def test_reject_incoming_order_requires_reason(
    auth_client, supplier_setup, settings_no_throttle
):
    company = supplier_setup["company"]
    store = supplier_setup["store"]
    order = IncomingOrder.objects.create(
        supplier=company,
        store=store,
        store_name=store.name,
        number="ORD-2026-0001",
        total_amount=Decimal("50000.00"),
    )
    IncomingOrderItem.objects.create(
        order=order,
        name="Suv 1L",
        unit="dona",
        quantity=Decimal("10"),
        price=Decimal("5000"),
        total=Decimal("50000"),
    )

    # No reason → 400
    r = auth_client.post(
        f"/api/supplier/orders/{order.id}/reject/",
        {},
        format="json",
    )
    assert r.status_code == 400, r.content

    r = auth_client.post(
        f"/api/supplier/orders/{order.id}/reject/",
        {"reason": "Omborda yo'q"},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["status"] == IncomingOrderStatus.REJECTED
    assert r.data["rejection_reason"] == "Omborda yo'q"


@pytest.mark.django_db
def test_kpi_dashboard_shape(auth_client, supplier_setup, settings_no_throttle):
    r = auth_client.get("/api/supplier/kpi/dashboard/")
    assert r.status_code == 200, r.content
    for key in (
        "active_stores",
        "total_stores",
        "today_invoices",
        "outstanding_payments",
        "monthly_revenue",
    ):
        assert key in r.data


@pytest.mark.django_db
def test_without_supplier_token_endpoints_403(supplier_setup, settings_no_throttle):
    """Plain store-portal JWT must not access supplier endpoints."""
    user = supplier_setup["user"]
    client = APIClient()
    # Token without supplier claim
    tokens = issue_token_pair(user, active_store_id=supplier_setup["company"].id)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    r = client.get("/api/supplier/stores/")
    assert r.status_code == 403, r.content


@pytest.mark.django_db
def test_select_supplier_endpoint(supplier_setup, settings_no_throttle):
    client = APIClient()
    tokens = issue_token_pair(supplier_setup["user"])
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    r = client.post(
        "/api/auth/select-supplier/",
        {"supplier_id": str(supplier_setup["company"].id)},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data["active_portal"] == "supplier"
    assert r.data["role"] == Role.SUPPLIER_ADMIN


@pytest.mark.django_db
def test_invoice_delete_only_draft(auth_client, supplier_setup, settings_no_throttle):
    company = supplier_setup["company"]
    store = supplier_setup["store"]
    inv = OutgoingInvoice.objects.create(
        supplier=company,
        store=store,
        number="ALP-2026-0099",
        status=OutgoingInvoiceStatus.DELIVERED,
        total_amount=Decimal("100.00"),
    )
    r = auth_client.delete(f"/api/supplier/invoices/{inv.id}/")
    assert r.status_code == 400, r.content

    inv.status = OutgoingInvoiceStatus.DRAFT
    inv.save()
    r = auth_client.delete(f"/api/supplier/invoices/{inv.id}/")
    assert r.status_code == 204, r.content
