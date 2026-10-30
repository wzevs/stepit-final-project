from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.clients.api_views import ClientShipmentViewSet
from apps.couriers.api_views import (
    CourierDeviceView,
    CourierLocationView,
    CourierMeView,
    CourierShipmentViewSet,
    CourierStatusView,
)

client_router = DefaultRouter()
client_router.register("shipments", ClientShipmentViewSet, basename="client-shipment")

courier_router = DefaultRouter()
courier_router.register("shipments", CourierShipmentViewSet, basename="courier-shipment")

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token-obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("client/", include(client_router.urls)),
    path("courier/me/", CourierMeView.as_view(), name="courier-me"),
    path("courier/status/", CourierStatusView.as_view(), name="courier-status"),
    path("courier/locations/", CourierLocationView.as_view(), name="courier-locations"),
    path("courier/devices/", CourierDeviceView.as_view(), name="courier-devices"),
    path("courier/", include(courier_router.urls)),
]
