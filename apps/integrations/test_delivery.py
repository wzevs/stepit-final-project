from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.management import call_command
from django.utils import timezone

from apps.integrations.delivery import deliver_webhook
from apps.integrations.models import Webhook, WebhookDelivery
from apps.integrations.services import serialize_payload, sign_payload
from apps.shipments.models import Shipment
from apps.shipments.services import assign_courier, transition

S = Shipment.Status


class _Ok:
    def getcode(self):
        return 200

    def read(self, _n=-1):
        return b"ok"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_process_outbox_posts_signed_webhook(
    shipment, courier, client_shop, django_capture_on_commit_callbacks
):
    Webhook.objects.create(client=client_shop, url="https://shop.example/hook", secret="s3cret")
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)
    row = WebhookDelivery.objects.get()

    def fake_urlopen(request, timeout=10):
        assert request.full_url == "https://shop.example/hook"
        body = request.data
        assert request.get_header("X-signature") == sign_payload("s3cret", body)
        assert serialize_payload(row.payload) == body
        return _Ok()

    with patch("apps.integrations.delivery.urlopen", fake_urlopen):
        call_command("process_outbox")
    row.refresh_from_db()
    assert row.delivered_at is not None
    assert row.response_status == 200
    assert row.next_retry_at is None


def test_webhook_http_error_schedules_retry(shipment, client_shop):
    hook = Webhook.objects.create(client=client_shop, url="https://shop.example/hook")
    row = WebhookDelivery.objects.create(
        webhook=hook,
        event="shipment.status_changed",
        payload={"event": "shipment.status_changed"},
        next_retry_at=timezone.now(),
    )

    def boom(request, timeout=10):
        raise HTTPError(request.full_url, 500, "fail", hdrs=None, fp=BytesIO(b"nope"))

    with patch("apps.integrations.delivery.urlopen", boom):
        assert deliver_webhook(row.pk) == "failed"
    row.refresh_from_db()
    assert row.delivered_at is None
    assert row.response_status == 500
    assert row.next_retry_at is not None
    assert row.attempts == 1
