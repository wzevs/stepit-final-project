from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.shipments.models import Shipment

from .models import TrackingToken


def build_tracking_url(raw_token: str) -> str:
    return f"{settings.PUBLIC_BASE_URL}/t/{raw_token}/"


def cap_token_expiry(shipment: Shipment, hours: int | None = None) -> int:
    """Shorten the lifetime of a finished shipment's active links to a grace period."""
    grace = hours if hours is not None else settings.TRACKING_TOKEN_GRACE_HOURS
    deadline = timezone.now() + timedelta(hours=grace)
    return TrackingToken.objects.filter(
        shipment=shipment, revoked_at__isnull=True, expires_at__gt=deadline
    ).update(expires_at=deadline)
