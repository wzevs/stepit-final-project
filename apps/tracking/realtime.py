from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.companies.live import live_couriers
from apps.couriers.models import CourierProfile
from apps.shipments.models import Shipment

from .services import public_live_payload

LIVE_STATUSES = (
    Shipment.Status.ASSIGNED,
    Shipment.Status.PICKED_UP,
    Shipment.Status.IN_TRANSIT,
    Shipment.Status.OUT_FOR_DELIVERY,
)


def company_group(company_id) -> str:
    return f"live.company.{company_id}"


def shipment_group(shipment_id) -> str:
    return f"live.shipment.{shipment_id}"


def broadcast_courier_location(courier: CourierProfile) -> None:
    """Push the new pin to the dispatcher map and to open public tracking pages."""
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        company_group(courier.company_id),
        {"type": "live.update", "payload": live_couriers(courier.company)},
    )
    shipments = Shipment.objects.filter(courier=courier, status__in=LIVE_STATUSES).select_related(
        "pickup_address", "delivery_address", "courier", "client"
    )
    for shipment in shipments:
        async_to_sync(layer.group_send)(
            shipment_group(shipment.pk),
            {"type": "live.update", "payload": public_live_payload(shipment)},
        )
