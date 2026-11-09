"""
How a parcel price is chosen.

1. District → district, when both neighbourhoods are known and that pair has a row.
2. Otherwise city → city.
3. Otherwise the company's standard tariff.
4. A weight band, when the parcel has a weight, is added on top of that route.
5. Home delivery is added last. It never replaces the route price.

The same rules are what the shop form shows before save, and what is copied
onto the shipment so a later tariff edit does not rewrite old parcels.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q

from apps.network.models import District, Tariff, WeightBand

BASIS_KA = {
    "district": "უბნებს შორის",
    "city": "ქალაქებს შორის",
    "standard": "სტანდარტული",
}


@dataclass(frozen=True)
class ShippingQuote:
    amount: Decimal
    route_fee: Decimal
    home_fee: Decimal
    weight_fee: Decimal
    basis: str
    weight_uncovered: bool = False

    @property
    def basis_ka(self) -> str:
        return BASIS_KA[self.basis]


def quote_shipping(
    *,
    company,
    origin: District | None,
    destination: District | None,
    home_delivery: bool,
    weight_kg: Decimal | None = None,
) -> ShippingQuote | None:
    route = None
    basis = None
    if origin is not None and destination is not None:
        route = Tariff.objects.filter(
            company=company,
            kind=Tariff.Kind.DISTRICT,
            is_active=True,
            origin_district=origin,
            destination_district=destination,
        ).first()
        if route is not None:
            basis = "district"
        else:
            route = Tariff.objects.filter(
                company=company,
                kind=Tariff.Kind.CITY,
                is_active=True,
                origin_city_id=origin.city_id,
                destination_city_id=destination.city_id,
            ).first()
            if route is not None:
                basis = "city"
    if route is None:
        route = Tariff.objects.filter(
            company=company, kind=Tariff.Kind.STANDARD, is_active=True
        ).first()
        basis = "standard" if route is not None else None
    if route is None or basis is None:
        return None
    home_fee = Decimal("0")
    if home_delivery:
        home = Tariff.objects.filter(company=company, kind=Tariff.Kind.HOME, is_active=True).first()
        if home is not None:
            home_fee = home.price
    weight_fee, uncovered = _weight_fee(company, weight_kg)
    return ShippingQuote(
        amount=route.price + weight_fee + home_fee,
        route_fee=route.price,
        home_fee=home_fee,
        weight_fee=weight_fee,
        basis=basis,
        weight_uncovered=uncovered,
    )


def _weight_fee(company, weight_kg: Decimal | None) -> tuple[Decimal, bool]:
    bands = WeightBand.objects.filter(company=company)
    if weight_kg is None or not bands.exists():
        return Decimal("0"), False
    match = (
        bands.filter(min_kg__lte=weight_kg)
        .filter(Q(max_kg__isnull=True) | Q(max_kg__gt=weight_kg))
        .order_by("-min_kg")
        .first()
    )
    if match is None:
        return Decimal("0"), True
    return match.surcharge, False
