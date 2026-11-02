from decimal import Decimal
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from apps.core.geo import city_center, geocode
from apps.shipments.creation import create_shipment


def test_city_center_known():
    lat, lng = city_center("Tbilisi")
    assert lat == Decimal("41.715100")
    assert lng == Decimal("44.827100")


def test_geocode_uses_nominatim_when_enabled(settings):
    settings.GEOCODER_ENABLED = True
    settings.GEOCODER_URL = "https://nominatim.openstreetmap.org/search"
    settings.GEOCODER_USER_AGENT = "test"
    payload = b'[{"lat":"41.7090","lon":"44.7930"}]'
    response = MagicMock()
    response.read.return_value = payload
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    with patch("apps.core.geo.urlopen", return_value=response) as opener:
        lat, lng = geocode("Tbilisi", "Rustaveli 1")
    assert lat == Decimal("41.7090")
    assert lng == Decimal("44.7930")
    assert "Rustaveli" in opener.call_args[0][0].full_url


def test_geocode_leaves_empty_when_nominatim_fails(settings):
    settings.GEOCODER_ENABLED = True
    with patch("apps.core.geo.urlopen", side_effect=URLError("down")):
        lat, lng = geocode("Batumi", "Rustaveli 2")
    assert lat is None
    assert lng is None


def test_geocode_off_does_not_invent_a_city_pin(settings):
    settings.GEOCODER_ENABLED = False
    assert geocode("Tbilisi", "Rustaveli 1") == (None, None)


def test_create_shipment_stores_street_pin(settings, client_shop):
    settings.GEOCODER_ENABLED = True
    payload = b'[{"lat":"41.701111","lon":"44.801111"}]'
    response = MagicMock()
    response.read.return_value = payload
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    with patch("apps.core.geo.urlopen", return_value=response):
        shipment, created = create_shipment(
            client=client_shop,
            source="manual",
            payload={
                "pickup_address": {"city": "Tbilisi", "line1": "Chavchavadze 5"},
                "delivery_address": {"city": "Tbilisi", "line1": "Rustaveli 12"},
                "recipient_name": "Nino",
                "recipient_phone": "555000111",
            },
        )
    assert created
    assert shipment.delivery_address.latitude == Decimal("41.701111")
    assert shipment.delivery_address.longitude == Decimal("44.801111")


def test_create_shipment_keeps_street_without_coords_when_lookup_misses(settings, client_shop):
    settings.GEOCODER_ENABLED = True
    with patch("apps.core.geo.urlopen", side_effect=URLError("down")):
        shipment, created = create_shipment(
            client=client_shop,
            source="manual",
            payload={
                "pickup_address": {"city": "Tbilisi", "line1": "Unknown alley 9"},
                "delivery_address": {"city": "Tbilisi", "line1": "Unknown alley 12"},
                "recipient_name": "Nino",
                "recipient_phone": "555000111",
            },
        )
    assert created
    assert shipment.delivery_address.line1 == "Unknown alley 12"
    assert shipment.delivery_address.latitude is None
    assert shipment.pickup_address.latitude is None
