from django.utils import timezone
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.couriers.models import Device
from apps.shipments.models import Shipment
from apps.shipments.services import InvalidTransition, ShipmentError, courier_allowed_next, transition
from apps.tracking.services import record_locations

from .permissions import IsCourier
from .serializers import (
    CourierMeSerializer,
    CourierShipmentSerializer,
    CourierStatusSerializer,
    DeviceSerializer,
    LocationBatchSerializer,
    TransitionSerializer,
)
from .throttling import CourierLocationThrottle


def _courier_shipments(courier):
    return Shipment.objects.filter(courier=courier).select_related(
        "client", "pickup_address", "delivery_address"
    )


class CourierAPIMixin:
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsCourier]


class CourierMeView(CourierAPIMixin, APIView):
    @extend_schema(tags=["courier"], summary="This courier's profile")
    def get(self, request):
        return Response(CourierMeSerializer(request.courier).data)


class CourierStatusView(CourierAPIMixin, APIView):
    @extend_schema(tags=["courier"], summary="Set online status", request=CourierStatusSerializer)
    def post(self, request):
        serializer = CourierStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        courier = request.courier
        courier.status = serializer.validated_data["status"]
        courier.save(update_fields=["status", "updated_at"])
        return Response(CourierMeSerializer(courier).data)


class CourierLocationView(CourierAPIMixin, APIView):
    throttle_classes = [CourierLocationThrottle]

    @extend_schema(
        tags=["courier"],
        summary="Upload GPS points",
        description="Send a batch. Noisy (>200 m) and future-dated fixes are dropped.",
        request=LocationBatchSerializer,
    )
    def post(self, request):
        serializer = LocationBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accepted = record_locations(request.courier, serializer.validated_data["points"])
        return Response({"accepted": accepted}, status=status.HTTP_202_ACCEPTED)


class CourierDeviceView(CourierAPIMixin, APIView):
    @extend_schema(tags=["courier"], summary="Register this tablet for push", request=DeviceSerializer)
    def post(self, request):
        serializer = DeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = _upsert_device(request.courier, serializer.validated_data)
        return Response(DeviceSerializer(device).data, status=status.HTTP_200_OK)


class ShipmentFilter(filters.FilterSet):
    class Meta:
        model = Shipment
        fields = ["status", "tracking_number"]


@extend_schema_view(
    list=extend_schema(tags=["courier"], summary="My parcels"),
    retrieve=extend_schema(tags=["courier"], summary="Parcel detail"),
)
class CourierShipmentViewSet(
    CourierAPIMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = CourierShipmentSerializer
    filterset_class = ShipmentFilter
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return _courier_shipments(self.request.courier).order_by("-created_at")

    @extend_schema(
        tags=["courier"],
        summary="Change parcel status",
        request=TransitionSerializer,
        responses=CourierShipmentSerializer,
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        shipment = self.get_object()
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        to_status = serializer.validated_data["status"]
        if to_status not in courier_allowed_next(shipment.status):
            return Response(
                {"detail": f"Transition {shipment.status} -> {to_status} is not allowed."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            transition(
                shipment,
                to_status,
                actor=request.user,
                note=serializer.validated_data.get("note") or "",
                latitude=serializer.validated_data.get("latitude"),
                longitude=serializer.validated_data.get("longitude"),
                failure_reason=serializer.validated_data.get("failure_reason") or "",
                received_by=serializer.validated_data.get("received_by") or "",
            )
        except (InvalidTransition, ShipmentError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        photo = serializer.validated_data.get("proof_photo")
        signature = serializer.validated_data.get("proof_signature")
        fields = []
        if photo:
            shipment.proof_photo = photo
            fields.append("proof_photo")
        if signature:
            shipment.proof_signature = signature
            fields.append("proof_signature")
        if fields:
            fields.append("updated_at")
            shipment.save(update_fields=fields)
        return Response(CourierShipmentSerializer(shipment).data)


def _upsert_device(courier, data) -> Device:
    now = timezone.now()
    token = data["fcm_token"]
    device_id = (data.get("device_id") or "").strip()
    device = None
    if device_id:
        device = Device.objects.filter(courier=courier, device_id=device_id).first()
    if device is None:
        device = Device.objects.filter(fcm_token=token).first()
    if device is None:
        device = Device(courier=courier, fcm_token=token)

    device.courier = courier
    device.fcm_token = token
    device.platform = data.get("platform") or Device.Platform.ANDROID
    if device_id:
        device.device_id = device_id
    if "model_name" in data:
        device.model_name = data.get("model_name") or ""
    if "app_version" in data:
        device.app_version = data.get("app_version") or ""
    device.is_active = True
    device.last_seen_at = now
    device.save()
    return device
