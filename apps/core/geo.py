import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

# Map default / tests only. Geocode never invents a city pin.
CITY_CENTERS: dict[str, tuple[Decimal, Decimal]] = {
    "tbilisi": (Decimal("41.715100"), Decimal("44.827100")),
    "თბილისი": (Decimal("41.715100"), Decimal("44.827100")),
    "batumi": (Decimal("41.616800"), Decimal("41.636700")),
    "ბათუმი": (Decimal("41.616800"), Decimal("41.636700")),
    "kutaisi": (Decimal("42.267900"), Decimal("42.694600")),
    "ქუთაისი": (Decimal("42.267900"), Decimal("42.694600")),
    "rustavi": (Decimal("41.549500"), Decimal("44.993000")),
    "რუსთავი": (Decimal("41.549500"), Decimal("44.993000")),
}


def city_center(city: str) -> tuple[Decimal, Decimal] | tuple[None, None]:
    if not city:
        return None, None
    return CITY_CENTERS.get(city.strip().casefold()) or CITY_CENTERS.get(city.strip()) or (None, None)


PIN_REQUIRED = "რუკაზე პინი დასვით."


def optional_coords(latitude, longitude) -> dict:
    """Return lat/lng for shipment create, or {} if the user did not drop a pin."""
    if latitude is None and longitude is None:
        return {}
    if latitude is None or longitude is None:
        raise ValueError("latitude and longitude must be set together")
    return {"latitude": latitude, "longitude": longitude}


def require_coords(latitude, longitude) -> dict:
    coords = optional_coords(latitude, longitude)
    if not coords:
        raise ValueError(PIN_REQUIRED)
    return coords


def geocode(city: str, line1: str = "") -> tuple[Decimal, Decimal] | tuple[None, None]:
    """
    Street lookup for shop API addresses that arrived without a pin.
    Guest/shop/manager forms require a pin and never call this. A miss
    leaves coordinates empty so a manager or courier can drop one later.
    """
    if settings.GEOCODER_ENABLED and (city or line1):
        return _nominatim(city, line1)
    return None, None


def set_pin(address, latitude, longitude) -> None:
    if latitude in ("", None) or longitude in ("", None):
        raise ValueError("latitude and longitude must be set together")
    try:
        coords = optional_coords(Decimal(str(latitude)), Decimal(str(longitude)))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("latitude and longitude must be set together") from exc
    address.latitude = coords["latitude"]
    address.longitude = coords["longitude"]
    address.save(update_fields=["latitude", "longitude", "updated_at"])


def _nominatim(city: str, line1: str) -> tuple[Decimal, Decimal] | tuple[None, None]:
    query = ", ".join(part for part in (line1.strip(), city.strip(), "Georgia") if part)
    if not query:
        return None, None
    params = urlencode(
        {
            "q": query,
            "format": "json",
            "limit": "1",
            "countrycodes": "ge",
        }
    )
    request = Request(
        f"{settings.GEOCODER_URL}?{params}",
        headers={
            "User-Agent": settings.GEOCODER_USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            rows = json.loads(response.read().decode() or "[]")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.info("Geocode skipped: %s", exc)
        return None, None
    if not rows:
        return None, None
    try:
        return Decimal(str(rows[0]["lat"])), Decimal(str(rows[0]["lon"]))
    except (KeyError, InvalidOperation, TypeError, IndexError):
        return None, None
