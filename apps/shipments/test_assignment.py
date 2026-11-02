import pytest
from django.core import mail

from apps.clients.models import Client
from apps.core.guest import WALKIN_CODE, activate_walk_in
from apps.couriers.models import CourierProfile
from apps.notifications.models import Notification
from apps.shipments.assignment import auto_assign_courier, pick_courier
from apps.shipments.models import Shipment
from apps.shipments.services import assign_courier, transition

S = Shipment.Status
pytestmark = pytest.mark.django_db


def test_pick_courier_prefers_available(company, courier_factory):
    courier_factory(email="busy@example.com", status=CourierProfile.Status.BUSY)
    free = courier_factory(email="free@example.com", status=CourierProfile.Status.AVAILABLE)
    courier_factory(email="off@example.com", status=CourierProfile.Status.OFFLINE)
    assert pick_courier(company).pk == free.pk


def test_pick_courier_skips_offline(company, courier_factory):
    courier_factory(email="off@example.com", status=CourierProfile.Status.OFFLINE)
    assert pick_courier(company) is None


def test_auto_assign_binds_lightest_load(company, client_shop, address, courier_factory):
    busy = courier_factory(email="busy@example.com", status=CourierProfile.Status.AVAILABLE)
    free = courier_factory(email="free@example.com", status=CourierProfile.Status.AVAILABLE)
    existing = Shipment.objects.create(
        company=company,
        client=client_shop,
        pickup_address=address,
        delivery_address=address,
        recipient_name="A",
        recipient_phone="1",
    )
    assign_courier(existing, busy)
    waiting = Shipment.objects.create(
        company=company,
        client=client_shop,
        pickup_address=address,
        delivery_address=address,
        recipient_name="B",
        recipient_phone="2",
    )
    assert auto_assign_courier(waiting).pk == free.pk
    waiting.refresh_from_db()
    assert waiting.status == S.ASSIGNED
    assert waiting.courier_id == free.pk


def test_walk_in_live_as_soon_as_assigned(company, address, courier_factory):
    walk = Client.objects.create(company=company, name="ფიზიკური პირები", code=WALKIN_CODE)
    shop = Shipment.objects.create(
        company=company,
        client=Client.objects.create(company=company, name="Shop", code="SHOPX"),
        pickup_address=address,
        delivery_address=address,
        recipient_name="Nino",
        recipient_phone="555000000",
    )
    person = Shipment.objects.create(
        company=company,
        client=walk,
        pickup_address=address,
        delivery_address=address,
        recipient_name="Nino",
        recipient_phone="555000111",
        metadata={"sender_name": "Giorgi", "sender_phone": "555111222"},
    )
    courier = courier_factory(email="on@example.com", status=CourierProfile.Status.AVAILABLE)
    assign_courier(shop, courier)
    assign_courier(person, courier)
    shop.refresh_from_db()
    person.refresh_from_db()
    assert not shop.is_live_trackable
    assert person.is_live_trackable
    transition(person, S.PICKED_UP)
    person.refresh_from_db()
    assert person.is_live_trackable
    transition(person, S.OUT_FOR_DELIVERY)
    transition(person, S.DELIVERED)
    person.refresh_from_db()
    assert not person.is_live_trackable


def test_activate_walk_in_queues_both_map_messages(company, address, courier_factory):
    walk = Client.objects.create(company=company, name="ფიზიკური პირები", code=WALKIN_CODE)
    courier_factory(email="on@example.com", status=CourierProfile.Status.AVAILABLE)
    shipment = Shipment.objects.create(
        company=company,
        client=walk,
        pickup_address=address,
        delivery_address=address,
        recipient_name="Nino",
        recipient_phone="555000111",
        recipient_email="nino@example.com",
        metadata={
            "sender_name": "Giorgi",
            "sender_phone": "555111222",
            "sender_email": "giorgi@example.com",
        },
    )
    access = activate_walk_in(shipment)
    shipment.refresh_from_db()
    assert shipment.courier_id is not None
    assert access["assigned"]
    assert "/t/" in access["sender_url"]
    assert "/t/" in access["recipient_url"]
    assert access["sender_url"] != access["recipient_url"]
    notes = Notification.objects.filter(shipment=shipment)
    assert set(notes.values_list("template", "channel", "recipient")) == {
        ("walk_in_created", Notification.Channel.EMAIL, "nino@example.com"),
        ("walk_in_created", Notification.Channel.SMS, "555000111"),
        ("walk_in_sender", Notification.Channel.EMAIL, "giorgi@example.com"),
        ("walk_in_sender", Notification.Channel.SMS, "555111222"),
    }
    assert all(n.status == Notification.Status.SENT for n in notes)
    assert {m.to[0] for m in mail.outbox} == {"giorgi@example.com", "nino@example.com"}
