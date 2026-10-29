from django.urls import path

from .views import CourierLogoutView, CourierShipmentListView

app_name = "courier"

urlpatterns = [
    path("shipments/", CourierShipmentListView.as_view(), name="shipment-list"),
    path("logout/", CourierLogoutView.as_view(), name="logout"),
]
