import pytest
from django.db import IntegrityError

from apps.shipments.models import Shipment, generate_tracking_number


def test_tracking_number_format():
    number = generate_tracking_number("GLX")
    prefix, code = number.split("-")
    assert prefix == "GLX"
    assert len(code) == 8
    assert not set(code) & set("O0I1")


def test_shipment_gets_tracking_number_on_create(shipment):
    assert shipment.tracking_number.startswith("GLX-")
    assert shipment.status == Shipment.Status.PENDING
    assert not shipment.is_live_trackable


def test_external_id_unique_per_client(company, client_shop, address):
    kwargs = dict(
        company=company,
        client=client_shop,
        pickup_address=address,
        delivery_address=address,
        recipient_name="A",
        recipient_phone="1",
        external_id="ORDER-1",
    )
    Shipment.objects.create(**kwargs)
    with pytest.raises(IntegrityError):
        Shipment.objects.create(**kwargs)


def test_blank_external_id_not_unique(company, client_shop, address):
    kwargs = dict(
        company=company,
        client=client_shop,
        pickup_address=address,
        delivery_address=address,
        recipient_name="A",
        recipient_phone="1",
    )
    Shipment.objects.create(**kwargs)
    Shipment.objects.create(**kwargs)
    assert Shipment.objects.count() == 2
