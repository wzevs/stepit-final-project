from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.shipments.models import Shipment
from apps.shipments.services import add_note, assign_courier, transition
from apps.tracking.models import TrackingToken
from apps.tracking.services import build_tracking_url, public_live_payload

S = Shipment.Status


def _token_url(raw: str, live: bool = False) -> str:
    name = "tracking:public-live" if live else "tracking:public"
    return reverse(name, kwargs={"token": raw})


def test_build_tracking_url_matches_the_page(shipment, settings):
    settings.PUBLIC_BASE_URL = "http://localhost:8000"
    _, raw = TrackingToken.issue(shipment)
    assert build_tracking_url(raw) == f"http://localhost:8000{_token_url(raw)}"


def test_valid_token_shows_status_not_phone(client, shipment):
    _, raw = TrackingToken.issue(shipment)
    response = client.get(_token_url(raw))
    body = response.content.decode()
    assert response.status_code == 200
    assert shipment.tracking_number in body
    assert "ელოდება აღებას" in body
    assert shipment.delivery_address.line1 in body
    assert shipment.recipient_phone not in body
    token = TrackingToken.objects.get(shipment=shipment)
    assert token.access_count == 1


def test_public_events_shown_private_notes_hidden(client, shipment):
    add_note(shipment, "SECRET-INTERNAL", is_public=False)
    add_note(shipment, "კარი დავტოვე", is_public=True)
    _, raw = TrackingToken.issue(shipment)
    body = client.get(_token_url(raw)).content.decode()
    assert "კარი დავტოვე" in body
    assert "SECRET-INTERNAL" not in body


def test_unknown_token_is_404(client, db):
    response = client.get(_token_url("not-a-real-token"))
    assert response.status_code == 404
    assert "აღარ მოქმედებს" in response.content.decode()


def test_expired_token_is_404(client, shipment):
    token, raw = TrackingToken.issue(shipment)
    token.expires_at = timezone.now() - timedelta(seconds=1)
    token.save(update_fields=["expires_at"])
    assert client.get(_token_url(raw)).status_code == 404


def test_revoked_token_is_404(client, shipment):
    _, raw = TrackingToken.issue(shipment)
    TrackingToken.revoke_all(shipment)
    assert client.get(_token_url(raw)).status_code == 404


def test_live_payload_hides_courier_until_out_for_delivery(shipment, courier):
    courier.last_latitude = 41.71
    courier.last_longitude = 44.79
    courier.last_location_at = timezone.now()
    courier.save()
    shipment.courier = courier
    shipment.save(update_fields=["courier"])
    payload = public_live_payload(shipment)
    assert payload["live"] is False
    assert payload["courier"] is None
    assert "555000000" not in str(payload)


def test_live_json_after_out_for_delivery(client, shipment, courier):
    courier.last_latitude = 41.71
    courier.last_longitude = 44.79
    courier.last_location_at = timezone.now()
    courier.save()
    assign_courier(shipment, courier)
    transition(shipment, S.PICKED_UP)
    transition(shipment, S.OUT_FOR_DELIVERY)
    _, raw = TrackingToken.issue(shipment)
    page = client.get(_token_url(raw))
    assert "კურიერი გზაშია თქვენკენ" in page.content.decode()
    response = client.get(_token_url(raw, live=True))
    assert response.status_code == 200
    data = response.json()
    assert data["live"] is True
    assert data["courier"]["latitude"] == 41.71
    assert data["courier"]["longitude"] == 44.79
    assert shipment.recipient_phone not in response.content.decode()
    assert "courier@example.com" not in response.content.decode()


def test_live_poll_does_not_increment_access_count(client, shipment):
    _, raw = TrackingToken.issue(shipment)
    client.get(_token_url(raw, live=True))
    client.get(_token_url(raw, live=True))
    token = TrackingToken.objects.get(shipment=shipment)
    assert token.access_count == 0
