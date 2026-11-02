from django.dispatch import receiver

from apps.shipments.models import Shipment
from apps.shipments.signals import shipment_status_changed

from .services import notify_recipient, notify_walk_in_parties

S = Shipment.Status

# status -> (template, include tracking link)
RECIPIENT_MESSAGES: dict[str, tuple[str, bool]] = {
    S.PICKED_UP: ("tracking_link", True),
    S.OUT_FOR_DELIVERY: ("out_for_delivery", True),
    S.DELIVERED: ("delivered", False),
    S.FAILED: ("failed", False),
}


@receiver(shipment_status_changed, dispatch_uid="notifications.notify_recipient_on_status")
def notify_recipient_on_status(sender, shipment, to_status, **kwargs):
    message = RECIPIENT_MESSAGES.get(to_status)
    if message is None:
        return
    if shipment.is_walk_in:
        if to_status == S.DELIVERED:
            notify_walk_in_parties(
                shipment,
                recipient_template="delivered",
                sender_template="delivered_sender",
                flush=True,
            )
        elif to_status == S.FAILED:
            notify_walk_in_parties(
                shipment,
                recipient_template="failed",
                sender_template="failed",
                flush=True,
            )
        return
    template, with_link = message
    notify_recipient(shipment, template, with_link=with_link)
