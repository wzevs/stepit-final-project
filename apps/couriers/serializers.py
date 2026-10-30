from urllib.parse import quote

from rest_framework import serializers

from apps.core.models import Address
from apps.couriers.models import CourierProfile, Device
from apps.shipments.models import Shipment
from apps.shipments.services import COURIER_ACTIONS, courier_allowed_next
from apps.tracking.services import MAX_POINTS_PER_REQUEST


def maps_dir_url(address: Address) -> str:
    if address.latitude is not None and address.longitude is not None:
        destination = f"{address.latitude},{address.longitude}"
    else:
        destination = quote(address.formatted or f"{address.city}, {address.line1}")
    return f"https://www.google.com/maps/dir/?api=1&destination={destination}"


class AddressSerializer(serializers.ModelSerializer):
    maps_url = serializers.SerializerMethodField()

    class Meta:
        model = Address
        fields = ("city", "line1", "line2", "notes", "latitude", "longitude", "formatted", "maps_url")

    def get_maps_url(self, obj):
        return maps_dir_url(obj)


class CourierMeSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    company_id = serializers.UUIDField(read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = CourierProfile
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "status",
            "vehicle_type",
            "vehicle_plate",
            "company_id",
            "company_name",
            "last_latitude",
            "last_longitude",
            "last_location_at",
        )


class CourierStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CourierProfile.Status.choices)


class CourierShipmentSerializer(serializers.ModelSerializer):
    pickup_address = AddressSerializer()
    delivery_address = AddressSerializer()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    shop_name = serializers.CharField(source="client.name", read_only=True)
    allowed_next = serializers.SerializerMethodField()

    class Meta:
        model = Shipment
        fields = (
            "id",
            "tracking_number",
            "status",
            "status_display",
            "allowed_next",
            "shop_name",
            "recipient_name",
            "recipient_phone",
            "pickup_address",
            "delivery_address",
            "description",
            "weight_kg",
            "payment_type",
            "cod_amount",
            "is_fragile",
            "notes",
            "scheduled_delivery_date",
            "failure_reason",
            "received_by",
            "picked_up_at",
            "delivered_at",
        )

    def get_allowed_next(self, obj):
        return sorted(courier_allowed_next(obj.status))


class TransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=sorted((value, value) for value in COURIER_ACTIONS))
    note = serializers.CharField(required=False, allow_blank=True, default="")
    failure_reason = serializers.CharField(required=False, allow_blank=True, default="")
    received_by = serializers.CharField(required=False, allow_blank=True, default="")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    proof_photo = serializers.ImageField(required=False)
    proof_signature = serializers.ImageField(required=False)

    def validate(self, attrs):
        has_lat = attrs.get("latitude") is not None
        has_lng = attrs.get("longitude") is not None
        if has_lat != has_lng:
            raise serializers.ValidationError("latitude and longitude must be set together.")
        if attrs["status"] == Shipment.Status.FAILED and not (attrs.get("failure_reason") or "").strip():
            raise serializers.ValidationError({"failure_reason": "Required when delivery fails."})
        return attrs


class LocationPointSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    accuracy = serializers.FloatField(required=False, allow_null=True)
    speed = serializers.FloatField(required=False, allow_null=True)
    heading = serializers.FloatField(required=False, allow_null=True)
    battery_pct = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=100)
    recorded_at = serializers.DateTimeField()


class LocationBatchSerializer(serializers.Serializer):
    points = LocationPointSerializer(many=True)

    def validate_points(self, value):
        if not value:
            raise serializers.ValidationError("Send at least one point.")
        if len(value) > MAX_POINTS_PER_REQUEST:
            raise serializers.ValidationError(f"At most {MAX_POINTS_PER_REQUEST} points per request.")
        return value


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = (
            "id",
            "platform",
            "fcm_token",
            "device_id",
            "model_name",
            "app_version",
            "is_active",
            "last_seen_at",
        )
        read_only_fields = ("id", "is_active", "last_seen_at")

    def validate_fcm_token(self, value):
        token = (value or "").strip()
        if not token:
            raise serializers.ValidationError("FCM token is required.")
        return token
