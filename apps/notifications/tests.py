from apps.notifications.models import Notification
from apps.shipments.models import Shipment
from apps.shipments.services import assign_courier, transition
from apps.tracking.models import TrackingToken

S = Shipment.Status


def test_pickup_queues_sms_with_tracking_link(shipment, courier, django_capture_on_commit_callbacks):
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)
    note = Notification.objects.get(shipment=shipment, template="tracking_link")
    assert note.channel == Notification.Channel.SMS
    assert note.status == Notification.Status.QUEUED
    assert note.recipient == shipment.recipient_phone
    assert "http://localhost:8000/t/" in note.body
    assert TrackingToken.objects.filter(shipment=shipment, sent_via="sms").count() == 1


def test_second_status_keeps_previous_link(shipment, courier, django_capture_on_commit_callbacks):
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)
    first_raw_url = Notification.objects.get(template="tracking_link").body
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.OUT_FOR_DELIVERY)
    assert TrackingToken.objects.filter(shipment=shipment, revoked_at__isnull=True).count() == 2
    assert Notification.objects.filter(template="out_for_delivery").exists()
    # The pickup SMS still contains a resolvable token.
    token = first_raw_url.rsplit("/t/", 1)[1].rstrip("/")
    assert TrackingToken.resolve(token) is not None


def test_email_channel_when_recipient_has_email(shipment, courier, django_capture_on_commit_callbacks):
    shipment.recipient_email = "nino@example.com"
    shipment.save(update_fields=["recipient_email"])
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)
    channels = set(Notification.objects.filter(shipment=shipment).values_list("channel", flat=True))
    assert channels == {Notification.Channel.SMS, Notification.Channel.EMAIL}


def test_company_can_disable_recipient_notifications(shipment, courier, django_capture_on_commit_callbacks):
    shipment.company.settings = {"notify_recipient": False}
    shipment.company.save(update_fields=["settings"])
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)
    assert Notification.objects.filter(shipment=shipment).count() == 0
