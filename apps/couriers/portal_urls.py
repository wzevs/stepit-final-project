from django.urls import path

from .views import CourierLogoutView, CourierMapView, CourierShipmentListView

app_name = "courier"

urlpatterns = [
    path("map/", CourierMapView.as_view(), name="map"),
    path("shipments/", CourierShipmentListView.as_view(), name="shipment-list"),
    path("logout/", CourierLogoutView.as_view(), name="logout"),
]
