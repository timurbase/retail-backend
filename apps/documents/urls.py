from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DocumentViewSet, RowActionsView

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")

urlpatterns = [
    *router.urls,
    path(
        "documents/<uuid:doc_id>/rows/<uuid:row_id>/<str:verb>/",
        RowActionsView.as_view(),
        name="document-row-action",
    ),
]
