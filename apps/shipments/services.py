"""
The only place where Shipment.status and Shipment.courier are changed.

Every change is written to ShipmentEvent inside the same transaction, and a
signal is sent after commit. Notifications, tracking links, webhooks and
(later) billing subscribe to those signals instead of being called from here.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.couriers.models import CourierProfile

from .models import Shipment, ShipmentEvent
from .signals import shipment_courier_changed, shipment_status_changed

logger = logging.getLogger(__name__)

S = Shipment.Status

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    S.DRAFT: frozenset({S.PENDING, S.CANCELLED}),
    S.PENDING: frozenset({S.ASSIGNED, S.CANCELLED}),
    S.ASSIGNED: frozenset({S.PICKED_UP, S.PENDING, S.CANCELLED}),
    S.PICKED_UP: frozenset({S.IN_TRANSIT, S.OUT_FOR_DELIVERY, S.RETURNED}),
    S.IN_TRANSIT: frozenset({S.OUT_FOR_DELIVERY, S.RETURNED}),
    S.OUT_FOR_DELIVERY: frozenset({S.DELIVERED, S.FAILED}),
    S.FAILED: frozenset({S.OUT_FOR_DELIVERY, S.IN_TRANSIT, S.RETURNED}),
    S.DELIVERED: frozenset(),
    S.RETURNED: frozenset(),
    S.CANCELLED: frozenset(),
}

COURIER_REQUIRED = frozenset({S.ASSIGNED, S.PICKED_UP, S.OUT_FOR_DELIVERY, S.DELIVERED, S.FAILED})

# Statuses in which the courier may be changed (handover between couriers).
REASSIGNABLE = frozenset({S.PENDING, S.ASSIGNED, S.PICKED_UP, S.IN_TRANSIT, S.FAILED})

# Moves the Android app may request. Cancel / return / assign stay on the company panel.
COURIER_ACTIONS = frozenset({S.PICKED_UP, S.IN_TRANSIT, S.OUT_FOR_DELIVERY, S.DELIVERED, S.FAILED})


class ShipmentError(Exception):
    pass


class InvalidTransition(ShipmentError):
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Transition {from_status} -> {to_status} is not allowed")


def allowed_next(status: str) -> frozenset[str]:
    return ALLOWED_TRANSITIONS.get(status, frozenset())


def can_transition(shipment: Shipment, to_status: str) -> bool:
    return to_status in allowed_next(shipment.status)


def courier_allowed_next(status: str) -> frozenset[str]:
    return allowed_next(status) & COURIER_ACTIONS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@transaction.atomic
def transition(
    shipment: Shipment,
    to_status: str,
    *,
    actor=None,
    note: str = "",
    latitude=None,
    longitude=None,
    failure_reason: str = "",
    received_by: str = "",
) -> ShipmentEvent:
    """
    Move a shipment to `to_status`. Courier assignment has its own functions:
    use assign_courier() / unassign_courier() for PENDING <-> ASSIGNED.
    """
    locked = _lock(shipment)
    from_status = locked.status

    if to_status == S.ASSIGNED or (from_status == S.ASSIGNED and to_status == S.PENDING):
        raise ShipmentError("Use assign_courier() / unassign_courier() to change the courier")
    if to_status not in allowed_next(from_status):
        raise InvalidTransition(from_status, to_status)
    if to_status in COURIER_REQUIRED and locked.courier_id is None:
        raise ShipmentError(f"A courier must be assigned before '{to_status}'")

    extra_fields: set[str] = set()
    if to_status == S.FAILED:
        if not failure_reason:
            raise ShipmentError("failure_reason is required when delivery fails")
        locked.failure_reason = failure_reason
        extra_fields.add("failure_reason")
    elif from_status == S.FAILED and locked.failure_reason:
        locked.failure_reason = ""
        extra_fields.add("failure_reason")
    if to_status == S.DELIVERED and received_by:
        locked.received_by = received_by
        extra_fields.add("received_by")

    event = _apply_status(
        locked,
        to_status,
        actor=actor,
        note=note or failure_reason,
        latitude=latitude,
        longitude=longitude,
        extra_fields=extra_fields,
    )
    _sync(shipment, locked)
    return event


@transaction.atomic
def assign_courier(
    shipment: Shipment, courier: CourierProfile, *, actor=None, note: str = ""
) -> ShipmentEvent | None:
    """
    Assign (or hand over to) a courier. PENDING shipments move to ASSIGNED.
    Returns None when the courier is already assigned (idempotent).
    """
    locked = _lock(shipment)

    if locked.status not in REASSIGNABLE:
        raise ShipmentError(f"Courier cannot be changed while shipment is '{locked.status}'")
    if courier.company_id != locked.company_id:
        raise ShipmentError("Courier belongs to another company")
    if not courier.is_active:
        raise ShipmentError("Courier is not active")
    if locked.courier_id == courier.pk:
        return None

    previous = locked.courier
    locked.courier = courier
    locked.save(update_fields=["courier", "updated_at"])

    event = ShipmentEvent.objects.create(
        shipment=locked,
        kind=ShipmentEvent.Kind.ASSIGNED,
        actor=actor,
        note=note,
        is_public=False,
        data={
            "courier_id": str(courier.pk),
            "previous_courier_id": str(previous.pk) if previous else None,
        },
    )
    if locked.status == S.PENDING:
        event = _apply_status(locked, S.ASSIGNED, actor=actor, note=note)

    _on_commit_courier_changed(locked, previous, courier, actor)
    _sync(shipment, locked)
    return event


@transaction.atomic
def unassign_courier(shipment: Shipment, *, actor=None, note: str = "") -> ShipmentEvent:
    """Remove the courier from an ASSIGNED shipment; it goes back to PENDING."""
    locked = _lock(shipment)

    if locked.status != S.ASSIGNED:
        raise ShipmentError("Only an assigned shipment that is not picked up yet can be unassigned")

    previous = locked.courier
    locked.courier = None
    locked.save(update_fields=["courier", "updated_at"])

    ShipmentEvent.objects.create(
        shipment=locked,
        kind=ShipmentEvent.Kind.UNASSIGNED,
        actor=actor,
        note=note,
        is_public=False,
        data={"previous_courier_id": str(previous.pk) if previous else None},
    )
    event = _apply_status(locked, S.PENDING, actor=actor, note=note)

    _on_commit_courier_changed(locked, previous, None, actor)
    _sync(shipment, locked)
    return event


def add_note(shipment: Shipment, note: str, *, actor=None, is_public: bool = False) -> ShipmentEvent:
    return ShipmentEvent.objects.create(
        shipment=shipment, kind=ShipmentEvent.Kind.NOTE, actor=actor, note=note, is_public=is_public
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _lock(shipment: Shipment) -> Shipment:
    return Shipment.objects.select_for_update().select_related("company", "courier").get(pk=shipment.pk)


def _sync(target: Shipment, source: Shipment) -> None:
    """Copy the fresh state back into the caller's instance."""
    target.refresh_from_db()
    target.courier = source.courier


def _apply_status(
    locked: Shipment,
    to_status: str,
    *,
    actor=None,
    note: str = "",
    latitude=None,
    longitude=None,
    extra_fields: set[str] | None = None,
) -> ShipmentEvent:
    from_status = locked.status
    now = timezone.now()
    fields = {"status", "updated_at", *(extra_fields or ())}

    locked.status = to_status
    if to_status == S.PICKED_UP and locked.picked_up_at is None:
        locked.picked_up_at = now
        fields.add("picked_up_at")
    if to_status == S.DELIVERED:
        locked.delivered_at = now
        fields.add("delivered_at")
    locked.save(update_fields=sorted(fields))

    if latitude is None and locked.courier is not None and locked.courier.last_latitude is not None:
        latitude, longitude = locked.courier.last_latitude, locked.courier.last_longitude

    event = ShipmentEvent.objects.create(
        shipment=locked,
        kind=ShipmentEvent.Kind.STATUS_CHANGE,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        note=note,
        latitude=latitude,
        longitude=longitude,
        is_public=True,
    )

    def send():
        _log_receiver_errors(
            shipment_status_changed.send_robust(
                sender=Shipment,
                shipment=locked,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                event=event,
            )
        )

    transaction.on_commit(send)
    return event


def _on_commit_courier_changed(shipment, previous, courier, actor) -> None:
    def send():
        _log_receiver_errors(
            shipment_courier_changed.send_robust(
                sender=Shipment, shipment=shipment, previous_courier=previous, courier=courier, actor=actor
            )
        )

    transaction.on_commit(send)


def _log_receiver_errors(responses) -> None:
    for receiver, result in responses:
        if isinstance(result, Exception):
            logger.error("Signal receiver %r failed", receiver, exc_info=result)
