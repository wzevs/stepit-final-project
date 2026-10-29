from django.urls import path

from .views import (
    ClientCreateView,
    ClientListView,
    CourierCreateView,
    CourierListView,
    ManageLoginView,
    ManageLogoutView,
    ShipmentDetailView,
    ShipmentListView,
    SwitchCompanyView,
)

app_name = "manage"

urlpatterns = [
    path("login/", ManageLoginView.as_view(), name="login"),
    path("logout/", ManageLogoutView.as_view(), name="logout"),
    path("switch/", SwitchCompanyView.as_view(), name="switch-company"),
    path("shipments/", ShipmentListView.as_view(), name="shipment-list"),
    path("shipments/<uuid:pk>/", ShipmentDetailView.as_view(), name="shipment-detail"),
    path("clients/", ClientListView.as_view(), name="client-list"),
    path("clients/new/", ClientCreateView.as_view(), name="client-create"),
    path("couriers/", CourierListView.as_view(), name="courier-list"),
    path("couriers/new/", CourierCreateView.as_view(), name="courier-create"),
]
