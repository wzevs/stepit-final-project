from decimal import Decimal

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from apps.core.models import Address
from apps.network.models import City, District, Tariff, Warehouse
from apps.network.quote import quote_shipping

pytestmark = pytest.mark.django_db


def _place(city_name, district_name):
    city, _ = City.objects.get_or_create(name=city_name)
    district, _ = District.objects.get_or_create(city=city, name=district_name)
    return district


def _money(company, kind, price, **extra):
    return Tariff.objects.create(company=company, kind=kind, price=price, **extra)


def test_district_pair_wins_over_city_and_standard(company):
    vake = _place("თბილისი", "ვაკე")
    saburtalo, _ = District.objects.get_or_create(city=vake.city, name="საბურთალო")
    _money(company, Tariff.Kind.STANDARD, Decimal("5"))
    _money(company, Tariff.Kind.CITY, Decimal("12"), origin_city=vake.city, destination_city=vake.city)
    _money(
        company,
        Tariff.Kind.DISTRICT,
        Decimal("4"),
        origin_district=vake,
        destination_district=saburtalo,
    )
    quote = quote_shipping(company=company, origin=vake, destination=saburtalo, home_delivery=False)
    assert quote.basis == "district"
    assert quote.amount == Decimal("4")


def test_city_pair_is_used_when_the_districts_have_no_row(company):
    vake = _place("თბილისი", "ვაკე")
    airport = _place("ბათუმი", "აეროპორტი")
    _money(company, Tariff.Kind.STANDARD, Decimal("5"))
    _money(company, Tariff.Kind.CITY, Decimal("15"), origin_city=vake.city, destination_city=airport.city)
    quote = quote_shipping(company=company, origin=vake, destination=airport, home_delivery=False)
    assert quote.basis == "city"
    assert quote.amount == Decimal("15")


def test_standard_is_the_fallback_and_home_delivery_is_added(company):
    _money(company, Tariff.Kind.STANDARD, Decimal("5"))
    _money(company, Tariff.Kind.HOME, Decimal("3"))
    quote = quote_shipping(company=company, origin=None, destination=None, home_delivery=True)
    assert quote.basis == "standard"
    assert quote.route_fee == Decimal("5")
    assert quote.home_fee == Decimal("3")
    assert quote.amount == Decimal("8")


def test_weight_band_is_added_between_the_route_and_home_delivery(company):
    from apps.network.models import WeightBand

    _money(company, Tariff.Kind.STANDARD, Decimal("5"))
    _money(company, Tariff.Kind.HOME, Decimal("3"))
    WeightBand.objects.create(company=company, min_kg=0, max_kg=1, surcharge=0)
    WeightBand.objects.create(company=company, min_kg=1, max_kg=5, surcharge=2)
    light = quote_shipping(
        company=company, origin=None, destination=None, home_delivery=True, weight_kg=Decimal("0.400")
    )
    assert light.weight_fee == Decimal("0")
    assert light.amount == Decimal("8")
    heavier = quote_shipping(
        company=company, origin=None, destination=None, home_delivery=True, weight_kg=Decimal("1")
    )
    assert heavier.weight_fee == Decimal("2")
    assert heavier.route_fee == Decimal("5")
    assert heavier.home_fee == Decimal("3")
    assert heavier.amount == Decimal("10")
    uncovered = quote_shipping(
        company=company, origin=None, destination=None, home_delivery=False, weight_kg=Decimal("9")
    )
    assert uncovered.weight_uncovered is True


def test_nothing_is_priced_until_a_standard_tariff_exists(company):
    vake = _place("თბილისი", "ვაკე")
    assert quote_shipping(company=company, origin=vake, destination=vake, home_delivery=True) is None


def test_a_city_tariff_cannot_omit_its_cities(company):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Tariff.objects.create(company=company, kind=Tariff.Kind.CITY, price=Decimal("1"))


def test_a_city_warehouse_cannot_store_a_district(company):
    district = _place("თბილისი", "ვაკე")
    address = Address.objects.create(city="თბილისი", line1="აღმაშენებელი 1", latitude=1, longitude=1)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Warehouse.objects.create(
                company=company,
                name="ჰაბი",
                kind=Warehouse.Kind.CITY,
                city=district.city,
                district=district,
                address=address,
            )


def test_database_rejects_overlapping_weight_bands(company):
    from apps.network.models import WeightBand

    if connection.vendor != "postgresql":
        pytest.skip("overlap is rejected by a PostgreSQL trigger")
    WeightBand.objects.create(company=company, min_kg=0, max_kg=2, surcharge=1)
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            WeightBand.objects.create(company=company, min_kg=1, max_kg=3, surcharge=4)


def test_postgres_rejects_a_district_from_another_city(company):
    if connection.vendor != "postgresql":
        pytest.skip("the city check is a PostgreSQL trigger")
    tbilisi = _place("თბილისი", "ვაკე")
    batumi = _place("ბათუმი", "აეროპორტი")
    address = Address.objects.create(city="თბილისი", line1="აღმაშენებელი 1", latitude=1, longitude=1)
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Warehouse.objects.create(
                company=company,
                name="არასწორი",
                kind=Warehouse.Kind.DISTRICT,
                city=tbilisi.city,
                district=batumi,
                address=address,
            )
