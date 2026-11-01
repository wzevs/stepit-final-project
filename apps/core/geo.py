from decimal import Decimal

# Street geocoding stays out of this stage. A city pin is enough for demo maps.
CITY_CENTERS: dict[str, tuple[Decimal, Decimal]] = {
    "tbilisi": (Decimal("41.715100"), Decimal("44.827100")),
    "თბილისი": (Decimal("41.715100"), Decimal("44.827100")),
    "batumi": (Decimal("41.616800"), Decimal("41.636700")),
    "ბათუმი": (Decimal("41.616800"), Decimal("41.636700")),
    "kutaisi": (Decimal("42.267900"), Decimal("42.694600")),
    "ქუთაისი": (Decimal("42.267900"), Decimal("42.694600")),
    "rustavi": (Decimal("41.549500"), Decimal("44.993000")),
    "რუსთავი": (Decimal("41.549500"), Decimal("44.993000")),
}


def city_center(city: str) -> tuple[Decimal, Decimal] | tuple[None, None]:
    if not city:
        return None, None
    return CITY_CENTERS.get(city.strip().casefold()) or CITY_CENTERS.get(city.strip()) or (None, None)
