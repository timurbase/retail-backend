from django.shortcuts import get_object_or_404
from rest_framework import status, views
from rest_framework.response import Response

from apps.audit.recorder import record
from apps.core.permissions import HasActiveStore, IsAdmin

from .models import CompanyInfo
from .serializers import CompanyInfoSerializer


class CompanyInfoView(views.APIView):
    """
    GET   /api/company/  — every authenticated member of the store
    PATCH /api/company/  — admin only
    """

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [HasActiveStore()]
        return [IsAdmin()]

    def get(self, request):
        company = get_object_or_404(CompanyInfo, store_id=request.active_store_id)
        return Response(CompanyInfoSerializer(company).data)

    def patch(self, request):
        company = get_object_or_404(CompanyInfo, store_id=request.active_store_id)
        serializer = CompanyInfoSerializer(company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = CompanyInfoSerializer(company).data
        serializer.save()
        after = serializer.data

        changes = [f"{k}: {before[k]} → {after[k]}" for k in after if before.get(k) != after.get(k)]
        record(
            request,
            action="update",
            object_type="company",
            object_id=str(company.store_id),
            object_label=company.name,
            details="; ".join(changes) or "tahrirlandi",
        )
        return Response(after, status=status.HTTP_200_OK)
