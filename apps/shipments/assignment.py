"""Choose a courier for a shipment without a dispatcher click."""

from django.db.models import Case, Count, IntegerField, Q, When

from apps.companies.live import ACTIVE_JOBS
from apps.couriers.models import CourierProfile

from .services import assign_courier


def pick_courier(company) -> CourierProfile | None:
    """
    Prefer an available courier, then a busy one, then the lightest load.
    Offline profiles are skipped so a parcel is not parked on a phone that is off.
    """
    return (
        CourierProfile.objects.filter(company=company, is_active=True)
        .exclude(status=CourierProfile.Status.OFFLINE)
        .annotate(active_jobs=Count("shipments", filter=Q(shipments__status__in=ACTIVE_JOBS)))
        .order_by(
            Case(
                When(status=CourierProfile.Status.AVAILABLE, then=0),
                default=1,
                output_field=IntegerField(),
            ),
            "active_jobs",
            "created_at",
        )
        .first()
    )


def auto_assign_courier(shipment, *, actor=None, note: str = "") -> CourierProfile | None:
    """Bind the shipment if a courier is online. No-op when already assigned."""
    if shipment.courier_id:
        return shipment.courier
    courier = pick_courier(shipment.company)
    if courier is None:
        return None
    assign_courier(shipment, courier, actor=actor, note=note or "ავტომატური მიბმა")
    return courier
