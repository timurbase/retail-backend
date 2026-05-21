from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import MxikSuggestView, ProductViewSet

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")

urlpatterns = [
    *router.urls,
    path("mxik/", MxikSuggestView.as_view(), name="mxik-suggest"),
]
