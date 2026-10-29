from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.integrations.authentication import ApiKeyAuthentication
from apps.shipments.creation import ShipmentCreateError, create_shipment
from apps.shipments.models import Shipment
from apps.shipments.services import InvalidTransition, ShipmentError, transition

from .permissions import IsClientActor
from .serializers import ShipmentCreateSerializer, ShipmentReadSerializer
from .throttling import ClientApiThrottle


class ShipmentFilter(filters.FilterSet):
    class Meta:
        model = Shipment
        fields = ["status", "external_id", "tracking_number"]


@extend_schema_view(
    list=extend_schema(tags=["client"], summary="List this shop's shipments"),
    retrieve=extend_schema(tags=["client"], summary="Shipment detail"),
    create=extend_schema(
        tags=["client"],
        summary="Create a shipment",
        description=(
            "Idempotent on external_id. Repeating a create with the same external_id "
            "returns 200 and the existing shipment instead of a duplicate."
        ),
        request=ShipmentCreateSerializer,
        responses={200: ShipmentReadSerializer, 201: ShipmentReadSerializer},
    ),
)
class ClientShipmentViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Shop API. Authenticate with X-API-Key, or with a staff user's JWT."""

    queryset = Shipment.objects.none()
    serializer_class = ShipmentReadSerializer
    authentication_classes = [ApiKeyAuthentication, JWTAuthentication]
    permission_classes = [IsClientActor]
    throttle_classes = [ClientApiThrottle]
    filterset_class = ShipmentFilter

    def get_queryset(self):
        return (
            Shipment.objects.filter(client=self.request.client)
            .select_related("pickup_address", "delivery_address")
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        serializer = ShipmentCreateSerializer(data=request.data, context={"client": request.client})
        serializer.is_valid(raise_exception=True)
        try:
            shipment, created = create_shipment(
                client=request.client,
                source=Shipment.Source.API,
                created_by=request.user,
                payload=serializer.validated_data,
            )
        except ShipmentCreateError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        body = ShipmentReadSerializer(shipment).data
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(
        tags=["client"], summary="Cancel a shipment", request=None, responses=ShipmentReadSerializer
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        shipment = self.get_object()
        actor = request.user if request.user.is_authenticated else None
        try:
            transition(shipment, Shipment.Status.CANCELLED, actor=actor)
        except (InvalidTransition, ShipmentError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ShipmentReadSerializer(shipment).data)
