"""Which courier company a client or a guest is asking for."""

from apps.companies.models import CourierCompany
from apps.couriers.models import CourierProfile

ANY = "any"


def company_choices() -> list[tuple[str, str]]:
    rows = [(ANY, "სულ ერთია")]
    companies = CourierCompany.objects.filter(is_active=True).order_by("name")
    rows.extend((str(company.pk), company.name) for company in companies)
    return rows


def resolve_company(value: str | None) -> CourierCompany | None:
    """A named company, or any active one. Any prefers a company with a free courier."""
    active = CourierCompany.objects.filter(is_active=True)
    if value and value != ANY:
        return active.filter(pk=value).first()
    with_courier = (
        active.filter(
            couriers__is_active=True,
            couriers__status=CourierProfile.Status.AVAILABLE,
        )
        .distinct()
        .order_by("created_at")
    )
    return with_courier.first() or active.order_by("created_at").first()
