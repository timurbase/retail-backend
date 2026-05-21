"""
Tenant models.

Store               — one retail location (the primary tenant).
Org                 — distributor parent (deferred per CLAUDE.md, NULL today).
CompanyInfo         — public-facing korxona profile shown in /sozlamalar.
"""

import uuid

from django.db import models

from apps.core.models import TimeStamped


class Plan(models.TextChoices):
    BETA = "beta", "Beta"
    PRO = "pro", "Pro"
    ENTERPRISE = "enterprise", "Enterprise"


class Org(TimeStamped):
    """Distributor-level tenant. Stays empty in the chakana-only rollout."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    stir = models.CharField(max_length=14, unique=True)

    class Meta:
        db_table = "tenants_org"

    def __str__(self) -> str:
        return self.name


class Store(TimeStamped):
    """Single retail shop. Every domain row carries store_id."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    org = models.ForeignKey(
        Org, on_delete=models.SET_NULL, null=True, blank=True, related_name="stores"
    )
    name = models.CharField(max_length=200)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.BETA)
    # Per-tenant config (CLAUDE.md: confidence threshold is per-tenant)
    mxik_confidence_threshold = models.FloatField(default=0.85)

    class Meta:
        db_table = "tenants_store"

    def __str__(self) -> str:
        return self.name


class SoliqOffice(TimeStamped):
    """Tax-authority tenant. Minimal today — registered users get
    read-only access to compliance dashboards via invite code."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    region = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "tenants_soliq_office"

    def __str__(self) -> str:
        return self.name


class CompanyInfo(TimeStamped):
    """Public profile of the store. 1:1 with Store, primary key shared.

    Mirrors lib/types.ts → CompanyInfo on the frontend.
    """

    store = models.OneToOneField(
        Store,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="company",
    )
    stir = models.CharField(max_length=14, unique=True)
    stir_verified = models.BooleanField(default=False)
    name = models.CharField(max_length=200)
    activity = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    director = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "tenants_company_info"

    def __str__(self) -> str:
        return f"{self.name} ({self.stir})"
