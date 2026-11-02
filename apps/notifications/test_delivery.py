from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.core import mail
from django.core.management import call_command

from apps.notifications.delivery import (
    deliver_notification,
    georgian_msisdn,
    process_notifications,
    send_ubill_sms,
)
from apps.notifications.models import Notification
from apps.shipments.models import Shipment
from apps.shipments.services import assign_courier, transition

S = Shipment.Status


def _queue_pickup(shipment, courier, django_capture_on_commit_callbacks):
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)


def test_process_outbox_sends_sms_and_email(shipment, courier, django_capture_on_commit_callbacks):
    shipment.recipient_email = "nino@example.com"
    shipment.save(update_fields=["recipient_email"])
    _queue_pickup(shipment, courier, django_capture_on_commit_callbacks)
    call_command("process_outbox")
    sms = Notification.objects.get(channel=Notification.Channel.SMS)
    email = Notification.objects.get(channel=Notification.Channel.EMAIL)
    assert sms.status == Notification.Status.SENT
    assert sms.provider_message_id == "console-sms"
    assert email.status == Notification.Status.SENT
    assert len(mail.outbox) == 1
    assert shipment.tracking_number in mail.outbox[0].subject
    assert "nino@example.com" in mail.outbox[0].to
    assert mail.outbox[0].alternatives


def test_email_failure_retries_then_fails(shipment, monkeypatch):
    note = Notification.objects.create(
        shipment=shipment,
        channel=Notification.Channel.EMAIL,
        recipient="nino@example.com",
        template="delivered",
        body="hello",
    )

    def boom(self, fail_silently=False):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("apps.notifications.delivery.EmailMultiAlternatives.send", boom)
    for _ in range(4):
        assert deliver_notification(note.pk) == "failed"
        note.refresh_from_db()
        assert note.status == Notification.Status.QUEUED
    assert deliver_notification(note.pk) == "failed"
    note.refresh_from_db()
    assert note.status == Notification.Status.FAILED
    assert note.attempts == 5


def test_georgian_msisdn_accepts_local_and_e164():
    assert georgian_msisdn("555123456") == "995555123456"
    assert georgian_msisdn("+995 555 123 456") == "995555123456"


def test_ubill_send_posts_json(settings):
    settings.UBILL_API_KEY = "secret"
    settings.UBILL_BRAND_ID = 7
    settings.UBILL_API_URL = "https://api.ubill.dev"
    settings.SMS_BODY_PREFIX = "Galaxy Express-ისგან. "
    payload = b'{"statusID": 0, "smsID": "abc"}'
    response = MagicMock()
    response.read.return_value = payload
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    with patch("apps.notifications.delivery.urlopen", return_value=response) as opener:
        assert send_ubill_sms("555000111", "hello") == "abc"
    request = opener.call_args[0][0]
    assert "key=secret" in request.full_url
    assert "brandID=7" in request.full_url
    assert "numbers=995555000111" in request.full_url
    assert "Galaxy%20Express" in request.full_url or "Galaxy+Express" in request.full_url


def test_ubill_http_error_raises(settings):
    settings.UBILL_API_KEY = "secret"
    settings.UBILL_BRAND_ID = 1
    settings.SMS_BODY_PREFIX = ""
    err = HTTPError("https://api.ubill.dev/v1/sms/send", 401, "no", hdrs={}, fp=BytesIO(b"nope"))
    with patch("apps.notifications.delivery.urlopen", side_effect=err):
        try:
            send_ubill_sms("555000111", "hello")
        except RuntimeError as exc:
            assert "401" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")


def test_already_sent_is_skipped(shipment):
    note = Notification.objects.create(
        shipment=shipment,
        channel=Notification.Channel.SMS,
        recipient="555",
        template="delivered",
        body="ok",
        status=Notification.Status.SENT,
    )
    assert process_notifications()["skipped"] == 0
    assert deliver_notification(note.pk) == "skipped"
