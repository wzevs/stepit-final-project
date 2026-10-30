from django.db.models import Count, Q
from django.utils import timezone

from apps.couriers.models import CourierProfile
from apps.shipments.models import Shipment

POLL_SECONDS = 4
STALE_AFTER_SEC = 120

ACTIVE_JOBS = (
    Shipment.Status.ASSIGNED,
    Shipment.Status.PICKED_UP,
    Shipment.Status.IN_TRANSIT,
    Shipment.Status.OUT_FOR_DELIVERY,
    Shipment.Status.FAILED,
)

COURIER_STATUS_KA = {
    CourierProfile.Status.OFFLINE: "გათიშული",
    CourierProfile.Status.AVAILABLE: "თავისუფალი",
    CourierProfile.Status.BUSY: "დაკავებული",
}


def live_couriers(company) -> dict:
    """Last known position for this company's couriers. Polled by the manager map."""
    now = timezone.now()
    rows = (
        CourierProfile.objects.filter(company=company, is_active=True)
        .select_related("user")
        .annotate(active_jobs=Count("shipments", filter=Q(shipments__status__in=ACTIVE_JOBS)))
        .order_by("user__first_name", "user__email")
    )
    couriers = []
    for courier in rows:
        age = None
        if courier.last_location_at is not None:
            age = max(0, int((now - courier.last_location_at).total_seconds()))
        lat = courier.last_latitude
        lng = courier.last_longitude
        couriers.append(
            {
                "id": str(courier.pk),
                "name": courier.user.get_full_name() or courier.user.email,
                "status": courier.status,
                "status_display": COURIER_STATUS_KA.get(courier.status, courier.status),
                "vehicle_type": courier.vehicle_type,
                "latitude": float(lat) if lat is not None else None,
                "longitude": float(lng) if lng is not None else None,
                "last_location_at": (
                    courier.last_location_at.isoformat() if courier.last_location_at else None
                ),
                "age_sec": age,
                "stale": age is None or age > STALE_AFTER_SEC,
                "active_jobs": courier.active_jobs,
            }
        )
    return {
        "couriers": couriers,
        "poll_interval_sec": POLL_SECONDS,
        "server_time": now.isoformat(),
    }
