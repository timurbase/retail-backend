from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI schema + docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # App APIs
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.tenants.urls")),
    path("api/", include("apps.audit.urls")),
    path("api/", include("apps.suppliers.urls")),
    path("api/", include("apps.products.urls")),
    path("api/", include("apps.documents.urls")),
    path("api/supplier/", include("apps.supplier_portal.urls")),
]
