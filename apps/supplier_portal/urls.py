from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("stores", views.SupplierStoreViewSet, basename="supplier-store")
router.register("products", views.SupplierProductViewSet, basename="supplier-product")
router.register("invoices", views.OutgoingInvoiceViewSet, basename="supplier-invoice")
router.register("orders", views.IncomingOrderViewSet, basename="supplier-order")
router.register("payments", views.PaymentRecordViewSet, basename="supplier-payment")
router.register(
    "demand-signals", views.DemandSignalViewSet, basename="supplier-demand"
)
router.register("routes", views.DeliveryRouteViewSet, basename="supplier-route")

urlpatterns = [
    path("company/", views.SupplierCompanyView.as_view(), name="supplier-company"),
    path("kpi/dashboard/", views.KpiDashboardView.as_view(), name="supplier-kpi"),
    path("insights/", views.InsightsView.as_view(), name="supplier-insights"),
    path("", include(router.urls)),
]
