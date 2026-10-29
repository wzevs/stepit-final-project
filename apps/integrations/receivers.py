from django.dispatch import receiver

from apps.shipments.signals import shipment_status_changed

from .services import STATUS_CHANGED, queue_webhooks, status_changed_payload


@receiver(shipment_status_changed, dispatch_uid="integrations.queue_status_webhooks")
def queue_status_webhooks(sender, shipment, event, **kwargs):
    queue_webhooks(shipment, STATUS_CHANGED, status_changed_payload(shipment, event))
