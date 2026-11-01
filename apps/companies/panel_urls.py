from django.urls import path
from django.views.generic import RedirectView

from .views import (
    ClientCreateView,
    ClientListView,
    CourierCreateView,
    CourierListView,
    LiveCouriersView,
    LiveMapView,
    ManageLoginView,
    ManageLogoutView,
    ShipmentDetailView,
    ShipmentLabelView,
    ShipmentListView,
    SwitchCompanyView,
)

app_name = "manage"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="manage:live-map", permanent=False)),
    path("login/", ManageLoginView.as_view(), name="login"),
    path("logout/", ManageLogoutView.as_view(), name="logout"),
    path("switch/", SwitchCompanyView.as_view(), name="switch-company"),
    path("shipments/", ShipmentListView.as_view(), name="shipment-list"),
    path("shipments/<uuid:pk>/", ShipmentDetailView.as_view(), name="shipment-detail"),
    path("shipments/<uuid:pk>/label/", ShipmentLabelView.as_view(), name="shipment-label"),
    path("clients/", ClientListView.as_view(), name="client-list"),
    path("clients/new/", ClientCreateView.as_view(), name="client-create"),
    path("map/", LiveMapView.as_view(), name="live-map"),
    path("live/", LiveCouriersView.as_view(), name="live-couriers"),
    path("couriers/", CourierListView.as_view(), name="courier-list"),
    path("couriers/new/", CourierCreateView.as_view(), name="courier-create"),
]
