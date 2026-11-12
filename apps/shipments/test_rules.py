from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.db.utils import DatabaseError
from django.utils import timezone

from apps.companies.models import CourierCompany
from apps.core.models import Address
from apps.couriers.models import CourierArea, CourierProfile
from apps.network.models import ShopTariff, Tariff, Warehouse
from apps.network.quote import quote_shipping
from apps.network.test_quote import _place
from apps.shipments.assignment import pick_courier
from apps.shipments.creation import ShipmentCreateError, create_shipment
from apps.shipments.models import CodLedger, Shipment
from apps.shipments.services import ShipmentError, assign_courier, transition

S = Shipment.Status
pytestmark = pytest.mark.django_db


def _address():
    return Address.objects.create(city="თბილისი", line1="აღმაშენებელი 1", latitude=1, longitude=1)


def _payload(**extra):
    data = {
        "pickup_address": {
            "city": "თბილისი",
            "line1": "ჭავჭავაძის 1",
            "latitude": Decimal("41.710000"),
            "longitude": Decimal("44.770000"),
        },
        "delivery_address": {
            "city": "თბილისი",
            "line1": "ვაჟა-ფშაველას 10",
            "latitude": Decimal("41.720000"),
            "longitude": Decimal("44.750000"),
        },
        "recipient_name": "ნინო",
        "recipient_phone": "555000111",
        "home_delivery": True,
    }
    data.update(extra)
    return data


def test_collecting_at_a_warehouse_skips_the_home_fee(company, client_shop):
    Tariff.objects.create(company=company, kind=Tariff.Kind.STANDARD, price=Decimal("5"))
    Tariff.objects.create(company=company, kind=Tariff.Kind.HOME, price=Decimal("3"))
    district = _place("თბილისი", "ვაკე")
    warehouse = Warehouse.objects.create(
        company=company,
        name="ვაკის საწყობი",
        kind=Warehouse.Kind.DISTRICT,
        city=district.city,
        district=district,
        address=_address(),
    )
    shipment, _ = create_shipment(
        client=client_shop,
        source=Shipment.Source.MANUAL,
        payload=_payload(destination_warehouse=warehouse, home_delivery=False),
    )
    assert shipment.home_delivery is False
    assert shipment.destination_warehouse_id == warehouse.pk
    assert shipment.home_fee == 0
    assert shipment.shipping_fee == Decimal("5")
    assert shipment.recipient_pin


def test_shop_tariff_replaces_only_the_company_standard(company, client_shop):
    Tariff.objects.create(company=company, kind=Tariff.Kind.STANDARD, price=Decimal("5"))
    ShopTariff.objects.create(company=company, client=client_shop, standard_price=Decimal("8"))
    own = quote_shipping(
        company=company, origin=None, destination=None, home_delivery=False, client=client_shop
    )
    assert own.basis == "shop"
    assert own.route_fee == Decimal("8")

    vake = _place("თბილისი", "ვაკე")
    saburtalo = _place("თბილისი", "საბურთალო")
    Tariff.objects.create(
        company=company,
        kind=Tariff.Kind.DISTRICT,
        price=Decimal("4"),
        origin_district=vake,
        destination_district=saburtalo,
    )
    pair = quote_shipping(
        company=company, origin=vake, destination=saburtalo, home_delivery=False, client=client_shop
    )
    assert pair.basis == "district"
    assert pair.route_fee == Decimal("4")


def test_pickup_window_must_sit_inside_branch_hours(company, client_shop, address):
    from apps.clients.models import PickupPoint

    point = PickupPoint.objects.create(
        client=client_shop,
        name="ვაკე",
        address=address,
        opens_at=time(10, 0),
        closes_at=time(18, 0),
    )
    with pytest.raises(ShipmentCreateError):
        create_shipment(
            client=client_shop,
            source=Shipment.Source.MANUAL,
            payload=_payload(
                pickup_point=point,
                pickup_address=None,
                pickup_window_start=time(9, 0),
                pickup_window_end=time(11, 0),
            ),
        )


def test_auto_assign_prefers_a_courier_who_covers_the_district(company, courier_factory):
    district = _place("თბილისი", "ვაკე")
    general = courier_factory(email="any@example.com", status=CourierProfile.Status.AVAILABLE)
    local = courier_factory(email="vake@example.com", status=CourierProfile.Status.BUSY)
    CourierArea.objects.create(courier=local, district=district)
    assert pick_courier(company, origin=district).pk == local.pk
    assert pick_courier(company).pk == general.pk


def test_delivery_needs_the_pin_and_cod_opens_a_ledger(company, client_shop, shipment, courier):
    shipment.recipient_pin = "2468"
    shipment.payment_type = Shipment.PaymentType.COD
    shipment.cod_amount = Decimal("12.50")
    shipment.save(update_fields=["recipient_pin", "payment_type", "cod_amount"])
    assign_courier(shipment, courier)
    transition(shipment, S.PICKED_UP)
    transition(shipment, S.OUT_FOR_DELIVERY)
    with pytest.raises(ShipmentError, match="PIN"):
        transition(shipment, S.DELIVERED, pod_pin="0000")
    transition(shipment, S.DELIVERED, pod_pin="2468", received_by="ნინო")
    shipment.refresh_from_db()
    assert shipment.pod_method == "pin"
    ledger = CodLedger.objects.get(shipment=shipment)
    assert ledger.amount == Decimal("12.50")
    assert ledger.settled_at is None
    assert ledger.courier_id == courier.pk
    assert ledger.client_id == client_shop.pk


def test_same_day_stops_at_the_cutoff_and_next_day_is_tomorrow(company, client_shop, monkeypatch):
    company.same_day_cutoff = time(15, 0)
    company.save(update_fields=["same_day_cutoff"])
    moment = timezone.make_aware(datetime(2026, 6, 2, 16, 30))
    monkeypatch.setattr("apps.shipments.creation.timezone.now", lambda: moment)
    with pytest.raises(ShipmentCreateError):
        create_shipment(
            client=client_shop,
            source=Shipment.Source.MANUAL,
            payload=_payload(service_level="same_day"),
        )
    shipment, _ = create_shipment(
        client=client_shop,
        source=Shipment.Source.MANUAL,
        payload=_payload(service_level="next_day"),
    )
    assert shipment.service_level == "next_day"
    assert shipment.scheduled_delivery_date == moment.date() + timedelta(days=1)


def test_database_rejects_a_warehouse_from_another_company(company, client_shop, shipment):
    if connection.vendor != "postgresql":
        pytest.skip("the company check is a PostgreSQL trigger")
    other = CourierCompany.objects.create(name="სხვა", slug="other", tracking_prefix="OTH")
    district = _place("თბილისი", "ვაკე")
    foreign = Warehouse.objects.create(
        company=other,
        name="სხვისი საწყობი",
        kind=Warehouse.Kind.CITY,
        city=district.city,
        address=_address(),
    )
    shipment.destination_warehouse = foreign
    shipment.home_delivery = False
    with pytest.raises(DatabaseError):
        shipment.save()
