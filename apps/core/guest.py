from apps.clients.models import Client
from apps.companies.models import CourierCompany
from apps.notifications.models import Notification
from apps.notifications.services import notify_walk_in_parties
from apps.shipments.assignment import auto_assign_courier
from apps.shipments.models import Shipment
from apps.tracking.services import issue_party_tracking_urls

WALKIN_CODE = "WALKIN"


def walk_in_client(company: CourierCompany | None = None) -> Client | None:
    """Shared client for guests who send a parcel without a shop account."""
    if company is None:
        from apps.companies.choice import resolve_company

        company = resolve_company(None)
    if company is None:
        return None
    client, _ = Client.objects.get_or_create(
        company=company,
        code=WALKIN_CODE,
        defaults={"name": "ფიზიკური პირები", "is_active": True},
    )
    return client


def activate_walk_in(shipment: Shipment) -> dict:
    """
    Bind a person-to-person parcel to an online courier and give both parties
    a live map link.
    """
    auto_assign_courier(shipment, note="ფიზიკური პირის ამანათი")
    sender_url, recipient_url = issue_party_tracking_urls(shipment)
    queued = notify_walk_in_parties(
        shipment,
        recipient_template="walk_in_created",
        sender_template="walk_in_sender",
        recipient_url=recipient_url,
        sender_url=sender_url,
        flush=True,
    )
    email_sent = False
    for note in queued:
        if note.channel != Notification.Channel.EMAIL:
            continue
        note.refresh_from_db()
        if note.status == Notification.Status.SENT:
            email_sent = True
        else:
            email_sent = False
            break
    return {
        "sender_url": sender_url,
        "recipient_url": recipient_url,
        "assigned": shipment.courier_id is not None,
        "email_sent": email_sent,
    }
