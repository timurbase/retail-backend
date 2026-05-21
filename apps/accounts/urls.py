from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from . import views

router = DefaultRouter()
router.register("users", views.TeamViewSet, basename="users")

urlpatterns = [
    path("send-otp/", views.SendOtpView.as_view(), name="send-otp"),
    path("verify-otp/", views.VerifyOtpView.as_view(), name="verify-otp"),
    path("register/", views.RegisterStoreView.as_view(), name="register-store"),
    path("select-store/", views.SelectStoreView.as_view(), name="select-store"),
    path("select-supplier/", views.SelectSupplierView.as_view(), name="select-supplier"),
    path("me/", views.MeView.as_view(), name="me"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", TokenBlacklistView.as_view(), name="logout"),
    path("", include(router.urls)),
]
