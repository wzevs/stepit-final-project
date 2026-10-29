from apps.integrations.models import Webhook, WebhookDelivery
from apps.integrations.services import sign_payload
from apps.shipments.models import Shipment
from apps.shipments.services import assign_courier, transition

S = Shipment.Status


def test_status_change_queues_webhook(shipment, courier, client_shop, django_capture_on_commit_callbacks):
    Webhook.objects.create(client=client_shop, url="https://shop.example/hook")
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)
    delivery = WebhookDelivery.objects.get()
    assert delivery.event == "shipment.status_changed"
    assert delivery.payload["shipment"]["tracking_number"] == shipment.tracking_number
    assert delivery.payload["shipment"]["status"] == S.PICKED_UP
    assert delivery.payload["shipment"]["previous_status"] == S.ASSIGNED


def test_webhook_event_filter(shipment, courier, client_shop, django_capture_on_commit_callbacks):
    Webhook.objects.create(
        client=client_shop, url="https://shop.example/only-delivered", events=["shipment.delivered"]
    )
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)
    assert WebhookDelivery.objects.count() == 0


def test_sign_payload_is_stable():
    body = b'{"a":1}'
    assert sign_payload("secret", body) == sign_payload("secret", body)
    assert sign_payload("secret", body) != sign_payload("other", body)
