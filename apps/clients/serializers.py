from rest_framework import serializers

from apps.clients.models import PickupPoint
from apps.core.models import Address
from apps.shipments.models import Shipment


class AddressInputSerializer(serializers.Serializer):
    country = serializers.CharField(max_length=2, required=False, default="GE")
    city = serializers.CharField(max_length=100)
    line1 = serializers.CharField(max_length=255)
    line2 = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        has_lat = attrs.get("latitude") is not None
        has_lng = attrs.get("longitude") is not None
        if has_lat != has_lng:
            raise serializers.ValidationError("latitude and longitude must be set together.")
        return attrs


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ("city", "line1", "line2", "latitude", "longitude", "formatted", "notes")


class ShipmentCreateSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    pickup_point = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.none(), required=False, allow_null=True
    )
    pickup_address = AddressInputSerializer(required=False)
    delivery_address = AddressInputSerializer()
    recipient_name = serializers.CharField(max_length=150)
    recipient_phone = serializers.CharField(max_length=20)
    recipient_email = serializers.EmailField(required=False, allow_blank=True, default="")
    description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    weight_kg = serializers.DecimalField(max_digits=7, decimal_places=3, required=False, allow_null=True)
    dimensions_cm = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    declared_value = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    payment_type = serializers.ChoiceField(
        choices=Shipment.PaymentType.choices, default=Shipment.PaymentType.PREPAID
    )
    cod_amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    is_fragile = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    scheduled_delivery_date = serializers.DateField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        client = self.context.get("client")
        if client is not None:
            self.fields["pickup_point"].queryset = PickupPoint.objects.filter(client=client, is_active=True)

    def validate(self, attrs):
        if not attrs.get("pickup_point") and not attrs.get("pickup_address"):
            raise serializers.ValidationError("Provide pickup_point or pickup_address.")
        if attrs.get("payment_type") == Shipment.PaymentType.COD and not attrs.get("cod_amount"):
            raise serializers.ValidationError(
                {"cod_amount": "Cash on delivery requires an amount greater than zero."}
            )
        return attrs


class ShipmentReadSerializer(serializers.ModelSerializer):
    pickup_address = AddressSerializer()
    delivery_address = AddressSerializer()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Shipment
        fields = (
            "id",
            "tracking_number",
            "external_id",
            "status",
            "status_display",
            "source",
            "recipient_name",
            "recipient_phone",
            "recipient_email",
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
            "delivered_at",
            "created_at",
        )
