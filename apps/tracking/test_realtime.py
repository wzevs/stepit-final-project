import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.utils import timezone

from apps.tracking.models import TrackingToken
from apps.tracking.realtime import broadcast_courier_location
from apps.tracking.services import record_locations
from config.asgi import application


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_public_socket_rejects_unknown_token():
    communicator = WebsocketCommunicator(application, "/ws/t/not-a-real-token/live/")
    connected, _ = await communicator.connect()
    assert connected is False


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_public_socket_sends_live_payload(shipment):
    _, raw = await sync_to_async(TrackingToken.issue)(shipment, sent_via="email")
    communicator = WebsocketCommunicator(application, f"/ws/t/{raw}/live/")
    connected, _ = await communicator.connect()
    assert connected is True
    payload = await communicator.receive_json_from()
    assert payload["tracking_number"] == shipment.tracking_number
    await communicator.disconnect()


@pytest.mark.django_db
def test_record_locations_broadcasts(courier, monkeypatch):
    seen = []

    def fake_broadcast(profile):
        seen.append(profile.pk)

    monkeypatch.setattr("apps.tracking.realtime.broadcast_courier_location", fake_broadcast)
    stored = record_locations(
        courier,
        [
            {
                "lat": "41.715100",
                "lng": "44.827100",
                "accuracy": 10,
                "recorded_at": timezone.now().isoformat(),
            }
        ],
    )
    assert stored == 1
    assert seen == [courier.pk]


def test_broadcast_without_listeners_does_not_raise(courier):
    broadcast_courier_location(courier)
