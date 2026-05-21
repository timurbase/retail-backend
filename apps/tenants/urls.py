from django.urls import path

from .views import CompanyInfoView

urlpatterns = [
    path("company/", CompanyInfoView.as_view(), name="company-info"),
]
