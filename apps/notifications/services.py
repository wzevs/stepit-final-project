from apps.shipments.models import Shipment, ShipmentEvent
from apps.tracking.models import TrackingToken
from apps.tracking.services import build_tracking_url

from .messages import render
from .models import Notification


def recipient_channels(shipment: Shipment) -> list[tuple[str, str]]:
    """(channel, address) pairs we can reach the recipient on."""
    channels = []
    if shipment.recipient_phone:
        channels.append((Notification.Channel.SMS, shipment.recipient_phone))
    if shipment.recipient_email:
        channels.append((Notification.Channel.EMAIL, shipment.recipient_email))
    return channels


def notify_recipient(shipment: Shipment, template: str, *, with_link: bool = False) -> list[Notification]:
    """
    Queue a message to the recipient on every available channel. With
    with_link, each channel gets its own tracking token (earlier links keep
    working). Actual sending is done by a background worker.
    """
    if not (shipment.company.settings or {}).get("notify_recipient", True):
        return []

    queued = []
    for channel, address in recipient_channels(shipment):
        context = {}
        if with_link:
            _, raw = TrackingToken.issue(shipment, sent_via=channel, revoke_existing=False)
            context["url"] = build_tracking_url(raw)
        queued.append(
            Notification.objects.create(
                shipment=shipment,
                channel=channel,
                recipient=address,
                template=template,
                body=render(template, shipment, **context),
            )
        )

    if queued:
        ShipmentEvent.objects.create(
            shipment=shipment,
            kind=ShipmentEvent.Kind.NOTIFICATION,
            note=f"{template} queued via {', '.join(n.channel for n in queued)}",
            is_public=False,
            data={"notification_ids": [n.pk for n in queued]},
        )
    return queued
