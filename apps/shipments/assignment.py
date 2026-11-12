"""Choose a courier for a shipment without a dispatcher click."""

from django.db.models import Case, Count, IntegerField, Q, When

from apps.companies.live import ACTIVE_JOBS
from apps.couriers.models import CourierProfile

from .services import assign_courier


def _ranked(company):
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
    )


def pick_courier(company, origin=None) -> CourierProfile | None:
    """
    Prefer an available courier, then a busy one, then the lightest load.
    When the pickup district is known, a courier who covers that district
    comes before a courier with no districts at all.
    Offline profiles are skipped so a parcel is not parked on a phone that is off.
    """
    ranked = _ranked(company)
    if origin is None:
        return ranked.first()
    covering = ranked.filter(areas__district=origin).first()
    if covering is not None:
        return covering
    return ranked.filter(areas__isnull=True).first()


def auto_assign_courier(shipment, *, actor=None, note: str = "") -> CourierProfile | None:
    """Bind the shipment if a courier is online. No-op when already assigned."""
    if shipment.courier_id:
        return shipment.courier
    courier = pick_courier(shipment.company, origin=shipment.origin_district)
    if courier is None:
        return None
    assign_courier(shipment, courier, actor=actor, note=note or "ავტომატური მიბმა")
    return courier
