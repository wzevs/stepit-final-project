"""Create a shipment for a client. Shared by the shop API and the dashboard."""

import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.clients.models import PickupPoint
from apps.core.geo import geocode
from apps.core.models import Address
from apps.network.models import Warehouse
from apps.network.quote import quote_shipping
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

    origin = payload.get("origin_district")
    if origin is None and pickup_point is not None and pickup_point.district_id:
        origin = pickup_point.district
    destination = payload.get("destination_district")
    warehouse = _warehouse(client, payload.get("destination_warehouse"), destination)
    if warehouse is not None and destination is None and warehouse.district_id:
        destination = warehouse.district
    home_delivery = bool(payload.get("home_delivery")) and warehouse is None
    if payload.get("home_delivery") and warehouse is not None:
        raise ShipmentCreateError({"destination_warehouse": "სახლამდე მიტანას საწყობი არ სჭირდება."})
    window_start, window_end = _pickup_window(pickup_point, payload)
    service_level, promised = _promise(client.company, payload)
    weight_kg = payload.get("weight_kg")
    quoted = quote_shipping(
        company=client.company,
        origin=origin,
        destination=destination,
        home_delivery=home_delivery,
        weight_kg=weight_kg,
        client=client,
    )
    if quoted is not None and quoted.weight_uncovered:
        raise ShipmentCreateError({"weight_kg": "ამ წონის საფეხური არ არის."})
    if warehouse is not None:
        delivery = _snapshot(warehouse.address)
    else:
        delivery = _create_address(payload["delivery_address"])

    return Shipment.objects.create(
        company=client.company,
        client=client,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        source=source,
        external_id=external_id,
        status=Shipment.Status.PENDING,
        pickup_point=pickup_point,
        pickup_address=pickup,
        delivery_address=delivery,
        recipient_name=payload["recipient_name"].strip(),
        recipient_phone=payload["recipient_phone"].strip(),
        recipient_email=(payload.get("recipient_email") or "").strip(),
        description=(payload.get("description") or "").strip(),
        weight_kg=weight_kg,
        dimensions_cm=(payload.get("dimensions_cm") or "").strip(),
        declared_value=payload.get("declared_value"),
        payment_type=payment_type,
        cod_amount=cod_amount,
        origin_district=origin,
        destination_district=destination,
        home_delivery=home_delivery,
        destination_warehouse=warehouse,
        service_level=service_level,
        pickup_window_start=window_start,
        pickup_window_end=window_end,
        recipient_pin=f"{secrets.randbelow(10000):04d}",
        shipping_fee=quoted.amount if quoted else None,
        route_fee=quoted.route_fee if quoted else None,
        home_fee=quoted.home_fee if quoted else 0,
        weight_fee=quoted.weight_fee if quoted else 0,
        tariff_basis=quoted.basis if quoted else "",
        is_fragile=bool(payload.get("is_fragile")),
        notes=(payload.get("notes") or "").strip(),
        scheduled_pickup_at=payload.get("scheduled_pickup_at"),
        scheduled_delivery_date=promised,
        metadata=payload.get("metadata") or {},
    )


def _warehouse(client, warehouse: Warehouse | None, destination):
    if warehouse is None:
        return None
    if warehouse.company_id != client.company_id or not warehouse.is_active:
        raise ShipmentCreateError({"destination_warehouse": "ეს საწყობი ამ კომპანიას არ ეკუთვნის."})
    if destination is not None and warehouse.city_id != destination.city_id:
        raise ShipmentCreateError(
            {"destination_warehouse": "საწყობი დანიშნულების ქალაქში უნდა იყოს."}
        )
    return warehouse


def _pickup_window(pickup_point, payload):
    start = payload.get("pickup_window_start")
    end = payload.get("pickup_window_end")
    if (start is None) != (end is None):
        raise ShipmentCreateError({"pickup_window_end": "აღების ინტერვალს ორივე დრო სჭირდება."})
    if start is not None and start >= end:
        raise ShipmentCreateError(
            {"pickup_window_end": "აღების დასასრული დასაწყისზე გვიან უნდა იყოს."}
        )
    if pickup_point is not None and pickup_point.opens_at and pickup_point.closes_at:
        if start is None:
            raise ShipmentCreateError(
                {"pickup_window_start": "ფილიალს საათები აქვს, აღების ინტერვალი აუცილებელია."}
            )
        if start < pickup_point.opens_at or end > pickup_point.closes_at:
            raise ShipmentCreateError(
                {"pickup_window_start": "აღების ინტერვალი ფილიალის საათებში უნდა ექცეოდეს."}
            )
    return start, end


def _promise(company, payload):
    level = (payload.get("service_level") or "").strip()
    if level not in {"same_day", "next_day"}:
        return "", payload.get("scheduled_delivery_date")
    moment = timezone.localtime(timezone.now())
    if level == "same_day":
        if moment.time() >= company.same_day_cutoff:
            raise ShipmentCreateError(
                {"service_level": "საჭრელი საათი გავიდა, დღეს აღარ ეწევა."}
            )
        return level, moment.date()
    return level, moment.date() + timedelta(days=1)


def _create_address(data: dict) -> Address:
    city = data["city"].strip()
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    if latitude is None or longitude is None:
        latitude, longitude = geocode(city, data.get("line1") or "")
    return Address.objects.create(
        country=(data.get("country") or "GE").strip() or "GE",
        city=city,
        line1=data["line1"].strip(),
        line2=(data.get("line2") or "").strip(),
        postal_code=(data.get("postal_code") or "").strip(),
        latitude=latitude,
        longitude=longitude,
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
    return PickupPoint.objects.filter(client=client, is_active=True).select_related(
        "address", "district", "district__city"
    )
