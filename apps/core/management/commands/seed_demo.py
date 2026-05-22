"""
Seed demo data: 4 users + Fergana stores + suppliers, fully linked.

Idempotent — re-running updates nothing destructive; objects are looked up
by stable natural keys (phone for users, STIR for tenants).

Usage (Railway shell):
    python manage.py seed_demo
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import (
    Membership,
    MembershipStatus,
    Portal,
    Role,
    User,
)
from apps.products.models import Product
from apps.suppliers.models import Supplier
from apps.supplier_portal.models import (
    BrandType,
    DemandHotness,
    DemandSignal,
    OutgoingInvoice,
    OutgoingInvoiceItem,
    OutgoingInvoiceStatus,
    SupplierCompany,
    SupplierProduct,
    SupplierProductCategory,
    SupplierStore,
    SupplierStoreStatus,
)
from apps.tenants.models import CompanyInfo, Plan, Store


class Command(BaseCommand):
    help = "Fergana demo data — 2 stores, 2 suppliers, 4 users, cross-linked."

    @transaction.atomic
    def handle(self, *args, **opts):
        out = self.stdout.write

        # ---------------- STORES (chakana tenant) ----------------
        store1, _ = Store.objects.update_or_create(
            name="Mehrigiyo Market",
            defaults={"plan": Plan.PRO, "mxik_confidence_threshold": 0.85},
        )
        CompanyInfo.objects.update_or_create(
            store=store1,
            defaults={
                "stir": "301234567",
                "stir_verified": True,
                "name": "Mehrigiyo Market MChJ",
                "activity": "Chakana savdo — oziq-ovqat",
                "address": "Farg'ona shahri, Al-Farg'oniy ko'chasi, 14",
                "director": "Sardor Karimov",
                "phone": "+998901111111",
                "email": "info@mehrigiyo.uz",
            },
        )

        store2, _ = Store.objects.update_or_create(
            name="Buyuk Birodarlar",
            defaults={"plan": Plan.BETA, "mxik_confidence_threshold": 0.85},
        )
        CompanyInfo.objects.update_or_create(
            store=store2,
            defaults={
                "stir": "302345678",
                "stir_verified": True,
                "name": "Buyuk Birodarlar YaTT",
                "activity": "Chakana savdo — uy-ro'zg'or",
                "address": "Farg'ona viloyati, Quva tumani, Mustaqillik 7",
                "director": "Dilshod Yusupov",
                "phone": "+998902222222",
            },
        )

        # ---------------- SUPPLIERS (distribyutor tenant) ----------------
        sup1, _ = SupplierCompany.objects.update_or_create(
            stir="304567890",
            defaults={
                "name": "Farg'ona Distribution Group",
                "director": "Bekzod Toshmatov",
                "phone": "+998903333333",
                "email": "sales@fdg.uz",
                "address": "Farg'ona shahri, Bog'i Eram MFY",
                "brand_type": BrandType.LOCAL,
                "region": "Farg'ona",
                "fleet_size": 8,
                "warehouse_address": "Farg'ona, Sanoat zonasi, ombor #4",
            },
        )

        sup2, _ = SupplierCompany.objects.update_or_create(
            stir="305678901",
            defaults={
                "name": "Marg'ilon Savdo Markazi",
                "director": "Aziza Olimova",
                "phone": "+998904444444",
                "email": "office@msm.uz",
                "address": "Marg'ilon shahri, Buyuk Ipak Yo'li 22",
                "brand_type": BrandType.EXCLUSIVE,
                "region": "Farg'ona",
                "fleet_size": 4,
                "warehouse_address": "Marg'ilon, Toshloq yo'li 5-km",
            },
        )

        # ---------------- USERS ----------------
        users_spec = [
            ("+998901111111", "Sardor Karimov", Portal.STORE, store1.id, Role.ADMIN, store1),
            ("+998902222222", "Dilshod Yusupov", Portal.STORE, store2.id, Role.ADMIN, store2),
            ("+998903333333", "Bekzod Toshmatov", Portal.SUPPLIER, sup1.id, Role.SUPPLIER_ADMIN, None),
            ("+998904444444", "Aziza Olimova", Portal.SUPPLIER, sup2.id, Role.SUPPLIER_ADMIN, None),
        ]
        for phone, name, portal, tenant_id, role, store_fk in users_spec:
            user, _ = User.objects.update_or_create(
                phone=phone,
                defaults={"full_name": name, "is_active": True},
            )
            Membership.objects.update_or_create(
                user=user,
                portal=portal,
                tenant_id=tenant_id,
                defaults={
                    "role": role,
                    "status": MembershipStatus.ACTIVE,
                    "store": store_fk,
                },
            )

        # ---------------- STORE → SUPPLIER DIRECTORY ----------------
        # Each store sees suppliers in its own directory (chakana side).
        for store, sup in [(store1, sup1), (store1, sup2), (store2, sup1)]:
            Supplier.objects.update_or_create(
                store=store,
                stir=sup.stir,
                defaults={"name": sup.name, "verified": True},
            )

        # ---------------- SUPPLIER → STORE CUSTOMER LIST ----------------
        sup1_store1, _ = SupplierStore.objects.update_or_create(
            supplier=sup1,
            stir="301234567",
            defaults={
                "store_id": store1.id,
                "name": "Mehrigiyo Market",
                "director": "Sardor Karimov",
                "phone": "+998901111111",
                "region": "Farg'ona",
                "district": "Farg'ona shahri",
                "status": SupplierStoreStatus.ACTIVE,
                "reliability_score": Decimal("9.2"),
                "monthly_volume": Decimal("12500000.00"),
                "total_lifetime_volume": Decimal("87000000.00"),
                "credit_limit": Decimal("15000000.00"),
                "outstanding_balance": Decimal("3200000.00"),
                "growth_percent": Decimal("18.50"),
                "last_order_at": timezone.now() - timedelta(days=3),
            },
        )
        SupplierStore.objects.update_or_create(
            supplier=sup1,
            stir="302345678",
            defaults={
                "store_id": store2.id,
                "name": "Buyuk Birodarlar",
                "director": "Dilshod Yusupov",
                "phone": "+998902222222",
                "region": "Farg'ona",
                "district": "Quva tumani",
                "status": SupplierStoreStatus.ACTIVE,
                "reliability_score": Decimal("8.4"),
                "monthly_volume": Decimal("6800000.00"),
                "total_lifetime_volume": Decimal("41000000.00"),
                "credit_limit": Decimal("8000000.00"),
                "outstanding_balance": Decimal("1100000.00"),
                "growth_percent": Decimal("12.20"),
                "last_order_at": timezone.now() - timedelta(days=7),
            },
        )
        SupplierStore.objects.update_or_create(
            supplier=sup2,
            stir="301234567",
            defaults={
                "store_id": store1.id,
                "name": "Mehrigiyo Market",
                "director": "Sardor Karimov",
                "phone": "+998901111111",
                "region": "Farg'ona",
                "district": "Farg'ona shahri",
                "status": SupplierStoreStatus.ACTIVE,
                "reliability_score": Decimal("9.0"),
                "monthly_volume": Decimal("4200000.00"),
                "total_lifetime_volume": Decimal("18000000.00"),
                "credit_limit": Decimal("5000000.00"),
                "outstanding_balance": Decimal("800000.00"),
                "growth_percent": Decimal("9.80"),
                "last_order_at": timezone.now() - timedelta(days=10),
            },
        )

        # ---------------- SUPPLIER PRODUCTS ----------------
        sup1_products = [
            ("Coca-Cola 1.5L", "10501001", SupplierProductCategory.ICHIMLIKLAR, "dona",
             Decimal("8500.00"), Decimal("4200")),
            ("Pepsi 1L", "10501002", SupplierProductCategory.ICHIMLIKLAR, "dona",
             Decimal("7200.00"), Decimal("3100")),
            ("Non — buxanka", "20203001", SupplierProductCategory.OZIQ_OVQAT, "dona",
             Decimal("3500.00"), Decimal("8500")),
            ("Guruch — Lazer 5kg", "20105003", SupplierProductCategory.OZIQ_OVQAT, "qop",
             Decimal("78000.00"), Decimal("450")),
        ]
        for name, mxik, cat, unit, price, stock in sup1_products:
            SupplierProduct.objects.update_or_create(
                supplier=sup1,
                name=name,
                defaults={
                    "mxik": mxik,
                    "category": cat,
                    "unit": unit,
                    "base_price": price,
                    "stock": stock,
                    "monthly_sales": stock * Decimal("0.6"),
                    "trend_percent": Decimal("12.50"),
                },
            )

        sup2_products = [
            ("Marlboro Red", "30302001", SupplierProductCategory.SIGARET, "qutiy",
             Decimal("28000.00"), Decimal("1200")),
            ("Atir — Chanel No.5 30ml", "40401001", SupplierProductCategory.KOSMETIKA, "dona",
             Decimal("450000.00"), Decimal("85")),
            ("Yuvish kukuni — Ariel 3kg", "50501001", SupplierProductCategory.MAISHIY, "qutiy",
             Decimal("62000.00"), Decimal("320")),
        ]
        for name, mxik, cat, unit, price, stock in sup2_products:
            SupplierProduct.objects.update_or_create(
                supplier=sup2,
                name=name,
                defaults={
                    "mxik": mxik,
                    "category": cat,
                    "unit": unit,
                    "base_price": price,
                    "stock": stock,
                    "monthly_sales": stock * Decimal("0.5"),
                    "trend_percent": Decimal("8.20"),
                },
            )

        # ---------------- STORE INVENTORY (mirror of supplier catalog) ----------------
        store_products = [
            (store1, "Coca-Cola 1.5L", "10501001", "dona", Decimal("250"), Decimal("9200")),
            (store1, "Non — buxanka", "20203001", "dona", Decimal("80"), Decimal("4000")),
            (store1, "Guruch — Lazer 5kg", "20105003", "qop", Decimal("40"), Decimal("82000")),
            (store2, "Pepsi 1L", "10501002", "dona", Decimal("180"), Decimal("7800")),
            (store2, "Yuvish kukuni — Ariel 3kg", "50501001", "qutiy", Decimal("25"), Decimal("66500")),
        ]
        for store, name, mxik, unit, qty, price in store_products:
            Product.objects.update_or_create(
                store=store,
                name=name,
                defaults={
                    "mxik": mxik,
                    "unit": unit,
                    "current_stock": qty,
                    "min_stock": qty * Decimal("0.2"),
                    "avg_price": price,
                    "last_received_at": timezone.now() - timedelta(days=2),
                },
            )

        # ---------------- INVOICES (sup1 → store1) ----------------
        invoice, _ = OutgoingInvoice.objects.update_or_create(
            supplier=sup1,
            number="INV-2026-0512",
            defaults={
                "store": sup1_store1,
                "status": OutgoingInvoiceStatus.DELIVERED,
                "sent_at": timezone.now() - timedelta(days=5),
                "due_date": date.today() + timedelta(days=10),
                "total_amount": Decimal("4_270_000.00"),
                "tracking_note": "Yetkazildi — qabul qilindi",
            },
        )
        invoice.items.all().delete()
        items = [
            ("Coca-Cola 1.5L", "10501001", "dona", Decimal("200"), Decimal("8500.00")),
            ("Non — buxanka", "20203001", "dona", Decimal("150"), Decimal("3500.00")),
            ("Guruch — Lazer 5kg", "20105003", "qop", Decimal("25"), Decimal("78000.00")),
        ]
        for name, mxik, unit, qty, price in items:
            OutgoingInvoiceItem.objects.create(
                invoice=invoice,
                name=name,
                mxik=mxik,
                unit=unit,
                quantity=qty,
                price=price,
                total=qty * price,
            )

        # ---------------- DEMAND SIGNALS (AI-driven trend mock) ----------------
        DemandSignal.objects.update_or_create(
            supplier=sup1,
            product_name="Coca-Cola 1.5L",
            region="Farg'ona",
            defaults={
                "district": "Farg'ona shahri",
                "weekly_volume": Decimal("980"),
                "trend_percent": Decimal("22.40"),
                "predicted_next_week": Decimal("1200"),
                "hotness": DemandHotness.RISING,
            },
        )
        DemandSignal.objects.update_or_create(
            supplier=sup2,
            product_name="Atir — Chanel No.5 30ml",
            region="Farg'ona",
            defaults={
                "district": "Marg'ilon",
                "weekly_volume": Decimal("18"),
                "trend_percent": Decimal("-4.10"),
                "predicted_next_week": Decimal("17"),
                "hotness": DemandHotness.FALLING,
            },
        )

        # ---------------- SUMMARY ----------------
        out(self.style.SUCCESS("\n✅ Seed muvaffaqiyatli yakunlandi.\n"))
        out("Stores (chakana):")
        out(f"  • {store1.name} — Farg'ona shahri")
        out(f"  • {store2.name} — Quva tumani\n")
        out("Suppliers (distribyutor):")
        out(f"  • {sup1.name} — fleet {sup1.fleet_size} ta")
        out(f"  • {sup2.name} — fleet {sup2.fleet_size} ta\n")
        out("Users (OTP kod sifatida 555555 ishlaydi):")
        for phone, name, portal, *_ in users_spec:
            out(f"  • {phone}  {name}  →  {portal} portal")
        out("\nBog'lanishlar: store1↔sup1, store1↔sup2, store2↔sup1")
        out(f"Invoice: {invoice.number}  —  {invoice.total_amount} UZS  ({invoice.status})")
