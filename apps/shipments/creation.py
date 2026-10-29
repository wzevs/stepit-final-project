"""Create a shipment for a client. Shared by the shop API and the dashboard."""

from django.db import IntegrityError, transaction

from apps.clients.models import PickupPoint
from apps.core.models import Address
from apps.shipments.models import Shipment


class ShipmentCreateError(Exception):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(str(detail))


def create_shipment(*, client, source: str, payload: dict, created_by=None) -> tuple[Shipment, bool]:
    """
    Returns (shipment, created). When external_id is set and this client already
    has that order, the existing shipment is returned and nothing is inserted.
    """
    external_id = (payload.get("external_id") or "").strip()
    if external_id:
        existing = Shipment.objects.filter(client=client, external_id=external_id).first()
        if existing:
            return existing, False

    try:
        with transaction.atomic():
            shipment = _insert(client, source, payload, external_id, created_by)
    except IntegrityError:
        if not external_id:
            raise
        existing = Shipment.objects.get(client=client, external_id=external_id)
        return existing, False
    return shipment, True


def _insert(client, source, payload, external_id, created_by) -> Shipment:
    pickup_point = payload.get("pickup_point")
    if pickup_point is not None:
        if pickup_point.client_id != client.id:
            raise ShipmentCreateError({"pickup_point": "Pickup point does not belong to this client."})
        if not pickup_point.is_active:
            raise ShipmentCreateError({"pickup_point": "Pickup point is not active."})

    pickup_data = payload.get("pickup_address")
    if pickup_data:
        pickup = _create_address(pickup_data)
    elif pickup_point is not None:
        pickup = _snapshot(pickup_point.address)
    else:
        raise ShipmentCreateError({"pickup_address": "Provide a pickup address or a pickup point."})

    payment_type = payload.get("payment_type") or Shipment.PaymentType.PREPAID
    cod_amount = payload.get("cod_amount") or 0
    if payment_type == Shipment.PaymentType.COD and cod_amount <= 0:
        raise ShipmentCreateError({"cod_amount": "Cash on delivery requires an amount greater than zero."})
    if payment_type != Shipment.PaymentType.COD:
        cod_amount = 0

    return Shipment.objects.create(
        company=client.company,
        client=client,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        source=source,
        external_id=external_id,
        status=Shipment.Status.PENDING,
        pickup_point=pickup_point,
        pickup_address=pickup,
        delivery_address=_create_address(payload["delivery_address"]),
        recipient_name=payload["recipient_name"].strip(),
        recipient_phone=payload["recipient_phone"].strip(),
        recipient_email=(payload.get("recipient_email") or "").strip(),
        description=(payload.get("description") or "").strip(),
        weight_kg=payload.get("weight_kg"),
        dimensions_cm=(payload.get("dimensions_cm") or "").strip(),
        declared_value=payload.get("declared_value"),
        payment_type=payment_type,
        cod_amount=cod_amount,
        is_fragile=bool(payload.get("is_fragile")),
        notes=(payload.get("notes") or "").strip(),
        scheduled_pickup_at=payload.get("scheduled_pickup_at"),
        scheduled_delivery_date=payload.get("scheduled_delivery_date"),
        metadata=payload.get("metadata") or {},
    )


def _create_address(data: dict) -> Address:
    return Address.objects.create(
        country=(data.get("country") or "GE").strip() or "GE",
        city=data["city"].strip(),
        line1=data["line1"].strip(),
        line2=(data.get("line2") or "").strip(),
        postal_code=(data.get("postal_code") or "").strip(),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        notes=(data.get("notes") or "").strip(),
    )


def _snapshot(source: Address) -> Address:
    """A new row, so later edits to the pickup point do not rewrite old shipments."""
    return Address.objects.create(
        country=source.country,
        city=source.city,
        line1=source.line1,
        line2=source.line2,
        postal_code=source.postal_code,
        latitude=source.latitude,
        longitude=source.longitude,
        google_place_id=source.google_place_id,
        formatted=source.formatted,
        notes=source.notes,
    )


def pickup_points_for(client):
    return PickupPoint.objects.filter(client=client, is_active=True).select_related("address")
