from datetime import timedelta

from django.utils import timezone

from apps.tracking.models import TrackingToken


def test_issue_and_resolve(shipment):
    token, raw = TrackingToken.issue(shipment, sent_via="sms")
    assert token.token_hash != raw
    assert len(raw) >= 43
    assert TrackingToken.resolve(raw).pk == token.pk


def test_reissue_revokes_previous(shipment):
    _, raw1 = TrackingToken.issue(shipment)
    _, raw2 = TrackingToken.issue(shipment)
    assert TrackingToken.resolve(raw1) is None
    assert TrackingToken.resolve(raw2) is not None


def test_expired_token_is_invalid(shipment):
    token, raw = TrackingToken.issue(shipment)
    token.expires_at = timezone.now() - timedelta(seconds=1)
    token.save(update_fields=["expires_at"])
    assert TrackingToken.resolve(raw) is None


def test_unknown_token(db):
    assert TrackingToken.resolve("not-a-real-token") is None
