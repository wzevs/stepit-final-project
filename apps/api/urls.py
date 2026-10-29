from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.clients.api_views import ClientShipmentViewSet

router = DefaultRouter()
router.register("shipments", ClientShipmentViewSet, basename="client-shipment")

urlpatterns = [
    path("client/", include(router.urls)),
]
