"""
TenantScopedViewSet — base ViewSet that auto-filters queryset to
request.active_store_id and stamps store_id on create.

Subclasses must set `queryset` (unfiltered) and `serializer_class`. They
inherit list/create/retrieve/update/partial_update/destroy.
"""

from __future__ import annotations

from rest_framework import viewsets

from apps.core.permissions import HasActiveStore


class TenantScopedViewSet(viewsets.ModelViewSet):
    permission_classes = (HasActiveStore,)

    def get_queryset(self):
        qs = super().get_queryset()
        store_id = getattr(self.request, "active_store_id", None)
        return qs.filter(store_id=store_id) if store_id else qs.none()

    def perform_create(self, serializer):
        serializer.save(store_id=self.request.active_store_id)
