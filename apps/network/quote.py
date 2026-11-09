"""
How a parcel price is chosen.

1. District → district, when both neighbourhoods are known and that pair has a row.
2. Otherwise city → city.
3. Otherwise the shop's own standard price, when that shop has one.
4. Otherwise the company's standard tariff.
5. A weight band, when the parcel has a weight, is added on top of that route.
6. Home delivery is added last, and only when the parcel goes to the door.

The same rules are what the shop form shows before save, and what is copied
onto the shipment so a later tariff edit does not rewrite old parcels.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q

from apps.network.models import District, ShopTariff, Tariff, WeightBand

BASIS_KA = {
    "district": "უბნებს შორის",
    "city": "ქალაქებს შორის",
    "shop": "მაღაზიის ტარიფი",
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
    client=None,
) -> ShippingQuote | None:
    route_price, basis = _route_price(company, origin, destination, client)
    if route_price is None or basis is None:
        return None
    home_fee = Decimal("0")
    if home_delivery:
        home = Tariff.objects.filter(company=company, kind=Tariff.Kind.HOME, is_active=True).first()
        if home is not None:
            home_fee = home.price
    weight_fee, uncovered = _weight_fee(company, weight_kg)
    return ShippingQuote(
        amount=route_price + weight_fee + home_fee,
        route_fee=route_price,
        home_fee=home_fee,
        weight_fee=weight_fee,
        basis=basis,
        weight_uncovered=uncovered,
    )


def _route_price(company, origin, destination, client):
    if origin is not None and destination is not None:
        district = Tariff.objects.filter(
            company=company,
            kind=Tariff.Kind.DISTRICT,
            is_active=True,
            origin_district=origin,
            destination_district=destination,
        ).first()
        if district is not None:
            return district.price, "district"
        city = Tariff.objects.filter(
            company=company,
            kind=Tariff.Kind.CITY,
            is_active=True,
            origin_city_id=origin.city_id,
            destination_city_id=destination.city_id,
        ).first()
        if city is not None:
            return city.price, "city"
    if client is not None:
        shop = ShopTariff.objects.filter(client=client).first()
        if shop is not None:
            return shop.standard_price, "shop"
    standard = Tariff.objects.filter(
        company=company, kind=Tariff.Kind.STANDARD, is_active=True
    ).first()
    if standard is None:
        return None, None
    return standard.price, "standard"


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
