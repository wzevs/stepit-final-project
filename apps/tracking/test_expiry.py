from datetime import timedelta

from django.utils import timezone

from apps.shipments.models import Shipment
from apps.shipments.services import assign_courier, transition
from apps.tracking.models import TrackingToken
from apps.tracking.services import cap_token_expiry

S = Shipment.Status


def test_final_status_caps_token_ttl(shipment, courier, django_capture_on_commit_callbacks, settings):
    settings.TRACKING_TOKEN_GRACE_HOURS = 24
    assign_courier(shipment, courier)
    with django_capture_on_commit_callbacks(execute=True):
        transition(shipment, S.PICKED_UP)
        transition(shipment, S.OUT_FOR_DELIVERY)
        transition(shipment, S.DELIVERED)
    token = TrackingToken.objects.filter(shipment=shipment, revoked_at__isnull=True).latest("created_at")
    remaining = token.expires_at - timezone.now()
    assert remaining <= timedelta(hours=24, minutes=1)


def test_cap_does_not_extend_already_short_ttl(shipment):
    token, _ = TrackingToken.issue(shipment, ttl_days=0)
    token.expires_at = timezone.now() + timedelta(hours=1)
    token.save(update_fields=["expires_at"])
    original = token.expires_at
    cap_token_expiry(shipment, hours=24)
    token.refresh_from_db()
    assert token.expires_at == original
