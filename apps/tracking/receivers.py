from django.dispatch import receiver

from apps.shipments.models import Shipment
from apps.shipments.signals import shipment_status_changed

from .services import cap_token_expiry

FINAL_STATUSES = {Shipment.Status.DELIVERED, Shipment.Status.RETURNED, Shipment.Status.CANCELLED}


@receiver(shipment_status_changed, dispatch_uid="tracking.cap_expiry_on_final_status")
def cap_expiry_on_final_status(sender, shipment, to_status, **kwargs):
    if to_status in FINAL_STATUSES:
        cap_token_expiry(shipment)
