import hashlib
import hmac
import json

from django.utils import timezone

from apps.shipments.models import Shipment, ShipmentEvent

from .models import Webhook, WebhookDelivery

STATUS_CHANGED = "shipment.status_changed"


def sign_payload(secret: str, body: bytes) -> str:
    """Value for the X-Signature header: hex HMAC-SHA256 of the raw request body."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def serialize_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode()


def status_changed_payload(shipment: Shipment, event: ShipmentEvent) -> dict:
    return {
        "event": STATUS_CHANGED,
        "occurred_at": event.created_at.isoformat(),
        "shipment": {
            "id": str(shipment.pk),
            "tracking_number": shipment.tracking_number,
            "external_id": shipment.external_id,
            "status": event.to_status,
            "previous_status": event.from_status,
        },
    }


def queue_webhooks(shipment: Shipment, event_name: str, payload: dict) -> list[WebhookDelivery]:
    """Write one outbox row per subscribed webhook; a worker delivers them."""
    hooks = Webhook.objects.filter(client_id=shipment.client_id, is_active=True)
    now = timezone.now()
    deliveries = [
        WebhookDelivery(webhook=hook, event=event_name, payload=payload, next_retry_at=now)
        for hook in hooks
        if not hook.events or event_name in hook.events
    ]
    return WebhookDelivery.objects.bulk_create(deliveries)
