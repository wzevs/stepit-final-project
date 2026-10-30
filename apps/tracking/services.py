from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.couriers.models import CourierProfile
from apps.shipments.models import Shipment

from .models import CourierLocation, TrackingToken

# GPS fixes noisier than this are dropped. The rest of the batch is kept.
MAX_ACCURACY_M = 200
# Phones with a slightly wrong clock still get through.
MAX_FUTURE_SKEW = timedelta(seconds=120)
MAX_POINTS_PER_REQUEST = 100


def build_tracking_url(raw_token: str) -> str:
    return f"{settings.PUBLIC_BASE_URL}/t/{raw_token}/"


def cap_token_expiry(shipment: Shipment, hours: int | None = None) -> int:
    """Shorten the lifetime of a finished shipment's active links to a grace period."""
    grace = hours if hours is not None else settings.TRACKING_TOKEN_GRACE_HOURS
    deadline = timezone.now() + timedelta(hours=grace)
    return TrackingToken.objects.filter(
        shipment=shipment, revoked_at__isnull=True, expires_at__gt=deadline
    ).update(expires_at=deadline)


def record_locations(courier: CourierProfile, points: list[dict]) -> int:
    """
    Append accepted GPS points and refresh CourierProfile.last_*.
    Returns how many points were stored. Noisy or future-dated fixes are skipped.
    """
    if len(points) > MAX_POINTS_PER_REQUEST:
        points = points[:MAX_POINTS_PER_REQUEST]

    now = timezone.now()
    rows: list[CourierLocation] = []
    for point in points:
        row = _to_location(courier, point, now)
        if row is not None:
            rows.append(row)
    if not rows:
        return 0

    last = rows[-1]
    with transaction.atomic():
        CourierLocation.objects.bulk_create(rows)
        CourierProfile.objects.filter(pk=courier.pk).update(
            last_latitude=last.latitude,
            last_longitude=last.longitude,
            last_location_at=last.recorded_at,
        )
    courier.last_latitude = last.latitude
    courier.last_longitude = last.longitude
    courier.last_location_at = last.recorded_at
    return len(rows)


def _to_location(courier: CourierProfile, point: dict, now) -> CourierLocation | None:
    recorded_at = point.get("recorded_at")
    if isinstance(recorded_at, str):
        recorded_at = parse_datetime(recorded_at)
    if recorded_at is None:
        return None
    if timezone.is_naive(recorded_at):
        recorded_at = timezone.make_aware(recorded_at, timezone.get_current_timezone())
    if recorded_at > now + MAX_FUTURE_SKEW:
        return None

    accuracy = point.get("accuracy")
    if accuracy is None:
        accuracy = point.get("accuracy_m")
    if accuracy is not None and accuracy > MAX_ACCURACY_M:
        return None

    try:
        latitude = Decimal(str(point["lat"] if "lat" in point else point["latitude"]))
        longitude = Decimal(str(point["lng"] if "lng" in point else point["longitude"]))
    except (KeyError, ArithmeticError, TypeError, ValueError):
        return None

    battery = point.get("battery_pct")
    heading = point.get("heading", point.get("heading_deg"))
    speed = point.get("speed", point.get("speed_mps"))
    return CourierLocation(
        courier=courier,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy,
        speed_mps=speed,
        heading_deg=heading,
        battery_pct=battery,
        recorded_at=recorded_at,
        received_at=now,
    )
