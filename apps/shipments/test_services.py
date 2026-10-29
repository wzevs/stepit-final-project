import pytest
from django.db import transaction

from apps.companies.models import CourierCompany
from apps.shipments.models import Shipment, ShipmentEvent
from apps.shipments.services import (
    InvalidTransition,
    ShipmentError,
    add_note,
    assign_courier,
    transition,
    unassign_courier,
)
from apps.shipments.signals import shipment_status_changed

S = Shipment.Status


def _assign(shipment, courier):
    assign_courier(shipment, courier)
    shipment.refresh_from_db()
    return shipment


def test_invalid_skip_is_rejected(shipment):
    with pytest.raises(InvalidTransition):
        transition(shipment, S.DELIVERED)


def test_cannot_transition_to_assigned_directly(shipment):
    with pytest.raises(ShipmentError, match="assign_courier"):
        transition(shipment, S.ASSIGNED)


def test_assign_moves_pending_to_assigned(shipment, courier):
    event = assign_courier(shipment, courier)
    shipment.refresh_from_db()
    assert shipment.status == S.ASSIGNED
    assert shipment.courier_id == courier.pk
    assert event.to_status == S.ASSIGNED
    kinds = list(shipment.events.values_list("kind", flat=True))
    assert ShipmentEvent.Kind.ASSIGNED in kinds
    assert ShipmentEvent.Kind.STATUS_CHANGE in kinds


def test_assign_is_idempotent(shipment, courier):
    assign_courier(shipment, courier)
    assert assign_courier(shipment, courier) is None


def test_cannot_assign_foreign_courier(shipment, courier_factory):
    other = CourierCompany.objects.create(name="Other", slug="other", tracking_prefix="OTH")
    foreign = courier_factory(email="foreign@example.com", company=other)
    with pytest.raises(ShipmentError, match="another company"):
        assign_courier(shipment, foreign)


def test_cannot_assign_inactive_courier(shipment, courier):
    courier.is_active = False
    courier.save(update_fields=["is_active"])
    with pytest.raises(ShipmentError, match="not active"):
        assign_courier(shipment, courier)


def test_handover_keeps_status(shipment, courier, courier_factory):
    other = courier_factory(email="second@example.com")
    _assign(shipment, courier)
    assign_courier(shipment, other)
    shipment.refresh_from_db()
    assert shipment.status == S.ASSIGNED
    assert shipment.courier_id == other.pk


def test_unassign_returns_to_pending(shipment, courier):
    _assign(shipment, courier)
    unassign_courier(shipment)
    shipment.refresh_from_db()
    assert shipment.status == S.PENDING
    assert shipment.courier_id is None


def test_cannot_unassign_after_pickup(shipment, courier):
    _assign(shipment, courier)
    transition(shipment, S.PICKED_UP)
    with pytest.raises(ShipmentError, match="unassigned"):
        unassign_courier(shipment)


def test_pickup_requires_courier(shipment):
    shipment.status = S.ASSIGNED
    shipment.save(update_fields=["status"])
    with pytest.raises(ShipmentError, match="courier"):
        transition(shipment, S.PICKED_UP)


def test_happy_path_sets_timestamps(shipment, courier):
    _assign(shipment, courier)
    transition(shipment, S.PICKED_UP)
    shipment.refresh_from_db()
    assert shipment.picked_up_at is not None
    transition(shipment, S.OUT_FOR_DELIVERY)
    transition(shipment, S.DELIVERED, received_by="Nino")
    shipment.refresh_from_db()
    assert shipment.status == S.DELIVERED
    assert shipment.delivered_at is not None
    assert shipment.received_by == "Nino"
    assert shipment.is_terminal
    with pytest.raises(InvalidTransition):
        transition(shipment, S.OUT_FOR_DELIVERY)


def test_failed_requires_reason_and_can_retry(shipment, courier):
    _assign(shipment, courier)
    transition(shipment, S.PICKED_UP)
    transition(shipment, S.OUT_FOR_DELIVERY)
    with pytest.raises(ShipmentError, match="failure_reason"):
        transition(shipment, S.FAILED)
    transition(shipment, S.FAILED, failure_reason="not home")
    shipment.refresh_from_db()
    assert shipment.failure_reason == "not home"
    transition(shipment, S.OUT_FOR_DELIVERY)
    shipment.refresh_from_db()
    assert shipment.failure_reason == ""


def test_add_note(shipment):
    event = add_note(shipment, "call first", is_public=True)
    assert event.kind == ShipmentEvent.Kind.NOTE
    assert event.is_public


def test_status_change_rolls_back_event_on_error(shipment, courier, monkeypatch):
    _assign(shipment, courier)
    original = Shipment.save

    def boom(self, *args, **kwargs):
        if self.status == S.PICKED_UP:
            raise RuntimeError("db down")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Shipment, "save", boom)
    with pytest.raises(RuntimeError):
        transition(shipment, S.PICKED_UP)
    shipment.refresh_from_db()
    assert shipment.status == S.ASSIGNED
    assert not shipment.events.filter(kind=ShipmentEvent.Kind.STATUS_CHANGE, to_status=S.PICKED_UP).exists()


def test_receiver_error_does_not_block_transition(shipment, courier, django_capture_on_commit_callbacks):
    def explode(**kwargs):
        raise RuntimeError("receiver exploded")

    shipment_status_changed.connect(explode, dispatch_uid="test.explode")
    try:
        _assign(shipment, courier)
        with django_capture_on_commit_callbacks(execute=True):
            transition(shipment, S.PICKED_UP)
    finally:
        shipment_status_changed.disconnect(explode, dispatch_uid="test.explode")
    shipment.refresh_from_db()
    assert shipment.status == S.PICKED_UP


def test_on_commit_does_not_fire_when_outer_transaction_rolls_back(shipment, courier):
    from apps.notifications.models import Notification

    _assign(shipment, courier)
    try:
        with transaction.atomic():
            transition(shipment, S.PICKED_UP)
            raise RuntimeError("abort")
    except RuntimeError:
        pass
    shipment.refresh_from_db()
    assert shipment.status == S.ASSIGNED
    assert Notification.objects.filter(shipment=shipment).count() == 0
