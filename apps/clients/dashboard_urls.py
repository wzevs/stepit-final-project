from django.urls import path

from .views import (
    DashboardLoginView,
    DashboardLogoutView,
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
    path("shipments/", ShipmentListView.as_view(), name="shipment-list"),
    path("shipments/new/", ShipmentCreateView.as_view(), name="shipment-create"),
    path("shipments/<uuid:pk>/", ShipmentDetailView.as_view(), name="shipment-detail"),
    path("shipments/<uuid:pk>/label/", ShipmentLabelView.as_view(), name="shipment-label"),
]
