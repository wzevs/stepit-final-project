from django.urls import path

from .views import (
    ApiAccessView,
    BranchFormView,
    BranchListView,
    DashboardLoginView,
    DashboardLogoutView,
    QuoteView,
    ShipmentCreateView,
    ShipmentDetailView,
    ShipmentLabelView,
    ShipmentListView,
    SwitchShopView,
)

app_name = "dashboard"

urlpatterns = [
    path("login/", DashboardLoginView.as_view(), name="login"),
    path("logout/", DashboardLogoutView.as_view(), name="logout"),
    path("switch/", SwitchShopView.as_view(), name="switch-shop"),
    path("api/", ApiAccessView.as_view(), name="api-access"),
    path("shipments/", ShipmentListView.as_view(), name="shipment-list"),
    path("shipments/new/", ShipmentCreateView.as_view(), name="shipment-create"),
    path("shipments/<uuid:pk>/", ShipmentDetailView.as_view(), name="shipment-detail"),
    path("shipments/<uuid:pk>/label/", ShipmentLabelView.as_view(), name="shipment-label"),
    path("branches/", BranchListView.as_view(), name="branch-list"),
    path("branches/new/", BranchFormView.as_view(), name="branch-create"),
    path("branches/<int:pk>/", BranchFormView.as_view(), name="branch-edit"),
    path("quote/", QuoteView.as_view(), name="quote"),
]
