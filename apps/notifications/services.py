from apps.shipments.models import Shipment, ShipmentEvent
from apps.tracking.models import TrackingToken
from apps.tracking.services import build_tracking_url

from .messages import render
from .models import Notification


def recipient_channels(shipment: Shipment) -> list[tuple[str, str]]:
    """(channel, address) pairs we can reach the recipient on."""
    channels = []
    if shipment.recipient_phone and not shipment.is_walk_in:
        channels.append((Notification.Channel.SMS, shipment.recipient_phone))
    if shipment.recipient_email:
        channels.append((Notification.Channel.EMAIL, shipment.recipient_email))
    return channels


def queue_message(
    shipment: Shipment, channel: str, address: str, template: str, **context
) -> Notification | None:
    address = (address or "").strip()
    if not address:
        return None
    return Notification.objects.create(
        shipment=shipment,
        channel=channel,
        recipient=address,
        template=template,
        body=render(template, shipment, **context),
    )


def queue_email(shipment: Shipment, address: str, template: str, **context) -> Notification | None:
    return queue_message(shipment, Notification.Channel.EMAIL, address, template, **context)


def notify_walk_in_parties(
    shipment: Shipment,
    *,
    recipient_template: str,
    sender_template: str,
    recipient_url: str = "",
    sender_url: str = "",
    flush: bool = False,
) -> list[Notification]:
    """
    Email and SMS to both people: the sender and the recipient have different
    addresses. SMS goes through uBill when it is configured.
    """
    meta = shipment.metadata or {}
    sender_name = meta.get("sender_name") or ""
    rec_ctx = {"url": recipient_url, "sender": sender_name}
    send_ctx = {"url": sender_url}
    queued = [
        queue_message(
            shipment, Notification.Channel.EMAIL, shipment.recipient_email, recipient_template, **rec_ctx
        ),
        queue_message(
            shipment, Notification.Channel.SMS, shipment.recipient_phone, recipient_template, **rec_ctx
        ),
        queue_message(
            shipment, Notification.Channel.EMAIL, meta.get("sender_email") or "", sender_template, **send_ctx
        ),
        queue_message(
            shipment, Notification.Channel.SMS, meta.get("sender_phone") or "", sender_template, **send_ctx
        ),
    ]
    queued = [note for note in queued if note is not None]
    if flush:
        from .delivery import deliver_notification

        for note in queued:
            deliver_notification(note.pk)
    return queued


def notify_recipient(
    shipment: Shipment,
    template: str,
    *,
    with_link: bool = False,
    url: str | None = None,
    **extra,
) -> list[Notification]:
    """
    Queue a message to the recipient on every available channel. With
    with_link, each channel gets its own tracking token (earlier links keep
    working) unless `url` is already provided. Actual sending is done by a
    background worker.
    """
    if not (shipment.company.settings or {}).get("notify_recipient", True):
        return []

    queued = []
    for channel, address in recipient_channels(shipment):
        context = dict(extra)
        if url:
            context["url"] = url
        elif with_link:
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
