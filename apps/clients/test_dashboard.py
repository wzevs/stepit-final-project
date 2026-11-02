import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client, ClientMembership
from apps.core.models import Address
from apps.integrations.models import ApiKey
from apps.shipments.models import Shipment

pytestmark = pytest.mark.django_db

_PINS = {
    "pickup_lat": "41.701111",
    "pickup_lng": "44.801111",
    "delivery_lat": "41.616111",
    "delivery_lng": "41.636111",
}


@pytest.fixture
def shop_user(client_shop):
    user = User.objects.create_user(email="shop@example.com", password="pass", role=User.Role.CLIENT_STAFF)
    ClientMembership.objects.create(user=user, client=client_shop, role=ClientMembership.Role.OPERATOR)
    return user


def test_login_and_empty_list(client, shop_user):
    assert client.login(username="shop@example.com", password="pass")
    response = client.get(reverse("dashboard:shipment-list"))
    assert response.status_code == 200
    assert "ამანათი ჯერ არ არის" in response.content.decode()


def test_user_without_a_shop_is_refused(client):
    user = User.objects.create_user(email="nobody@example.com", password="pass")
    client.force_login(user)
    response = client.get(reverse("dashboard:shipment-list"))
    assert response.status_code == 403


def test_manual_create_and_detail(client, shop_user, client_shop):
    client.force_login(shop_user)
    response = client.post(
        reverse("dashboard:shipment-create"),
        {
            "external_id": "POS-1",
            "pickup_city": "Tbilisi",
            "pickup_line1": "Chavchavadze 5",
            "delivery_city": "Batumi",
            "delivery_line1": "Rustaveli 2",
            "recipient_name": "Nino",
            "recipient_phone": "+995555000222",
            "payment_type": "prepaid",
            **_PINS,
        },
    )
    shipment = Shipment.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("dashboard:shipment-detail", args=[shipment.pk])
    assert shipment.source == Shipment.Source.MANUAL
    assert shipment.created_by == shop_user
    assert shipment.delivery_address.city == "Batumi"
    assert str(shipment.delivery_address.latitude) == "41.616111"

    page = client.get(response.url)
    assert shipment.tracking_number in page.content.decode()


def test_repeat_order_number_opens_the_existing_shipment(client, shop_user):
    client.force_login(shop_user)
    payload = {
        "external_id": "POS-1",
        "pickup_city": "Tbilisi",
        "pickup_line1": "Chavchavadze 5",
        "delivery_city": "Batumi",
        "delivery_line1": "Rustaveli 2",
        "recipient_name": "Nino",
        "recipient_phone": "+995555000222",
        "payment_type": "prepaid",
        **_PINS,
    }
    client.post(reverse("dashboard:shipment-create"), payload)
    client.post(reverse("dashboard:shipment-create"), {**payload, "recipient_name": "Other"})
    assert Shipment.objects.count() == 1
    assert Shipment.objects.get().recipient_name == "Nino"


def test_other_shop_shipment_is_hidden(client, shop_user, company, address):
    client.force_login(shop_user)
    other = Client.objects.create(company=company, name="Shop Two", code="SHOP2")
    shipment = Shipment.objects.create(
        company=company,
        client=other,
        pickup_address=address,
        delivery_address=Address.objects.create(city="Kutaisi", line1="Main 1"),
        recipient_name="A",
        recipient_phone="1",
    )
    response = client.get(reverse("dashboard:shipment-detail", args=[shipment.pk]))
    assert response.status_code == 404


def test_shop_form_keeps_map_pins(client, shop_user):
    client.force_login(shop_user)
    response = client.post(
        reverse("dashboard:shipment-create"),
        {
            "pickup_city": "Tbilisi",
            "pickup_line1": "Chavchavadze 5",
            "delivery_city": "Batumi",
            "delivery_line1": "Rustaveli 2",
            "recipient_name": "Nino",
            "recipient_phone": "+995555000222",
            "payment_type": "prepaid",
            **_PINS,
        },
    )
    shipment = Shipment.objects.select_related("pickup_address", "delivery_address").get()
    assert response.status_code == 302
    assert str(shipment.pickup_address.latitude) == "41.701111"
    assert str(shipment.delivery_address.latitude) == "41.616111"


def test_shop_can_mark_cash_on_delivery(client, shop_user):
    client.force_login(shop_user)
    response = client.post(
        reverse("dashboard:shipment-create"),
        {
            "pickup_city": "Tbilisi",
            "pickup_line1": "Chavchavadze 5",
            "delivery_city": "Batumi",
            "delivery_line1": "Rustaveli 2",
            "recipient_name": "Nino",
            "recipient_phone": "+995555000222",
            "payment_type": "cod",
            "cod_amount": "18.50",
            **_PINS,
        },
    )
    shipment = Shipment.objects.get()
    assert response.status_code == 302
    assert shipment.payment_type == Shipment.PaymentType.COD
    assert str(shipment.cod_amount) == "18.50"
    page = client.get(reverse("dashboard:shipment-create"))
    body = page.content.decode()
    assert "ნაღდი ადგილზე" in body
    assert 'name="payment_type"' in body
    assert 'id="pickup-map"' in body
    assert 'id="delivery-map"' in body


def test_form_requires_pins(client, shop_user):
    client.force_login(shop_user)
    response = client.post(
        reverse("dashboard:shipment-create"),
        {
            "pickup_city": "Tbilisi",
            "pickup_line1": "Chavchavadze 5",
            "delivery_city": "Batumi",
            "delivery_line1": "Rustaveli 2",
            "recipient_name": "Nino",
            "recipient_phone": "+995555000222",
            "payment_type": "prepaid",
        },
    )
    assert response.status_code == 200
    assert Shipment.objects.count() == 0
    assert "პინი" in response.content.decode()


def test_form_requires_a_pickup(client, shop_user):
    client.force_login(shop_user)
    response = client.post(
        reverse("dashboard:shipment-create"),
        {
            "delivery_city": "Batumi",
            "delivery_line1": "Rustaveli 2",
            "recipient_name": "Nino",
            "recipient_phone": "+995555000222",
            "payment_type": "prepaid",
        },
    )
    assert response.status_code == 200
    assert Shipment.objects.count() == 0


def test_shop_cancels_and_copies_tracking_link(client, shop_user, shipment):
    client.force_login(shop_user)
    detail = reverse("dashboard:shipment-detail", args=[shipment.pk])
    link = client.post(detail, {"intent": "tracking_link"})
    assert link.status_code == 302
    page = client.get(detail)
    assert "/t/" in page.content.decode()
    assert client.get(reverse("dashboard:shipment-label", args=[shipment.pk])).status_code == 200

    cancelled = client.post(detail, {"intent": "cancel"})
    assert cancelled.status_code == 302
    shipment.refresh_from_db()
    assert shipment.status == Shipment.Status.CANCELLED


def test_shop_issues_and_revokes_an_api_key(client, shop_user, client_shop):
    client.force_login(shop_user)
    page = client.get(reverse("dashboard:api-access"))
    assert page.status_code == 200
    assert "გასაღები ჯერ არ არის" in page.content.decode()

    created = client.post(reverse("dashboard:api-access"), {"intent": "issue", "name": "ERP"})
    assert created.status_code == 302
    key = ApiKey.objects.get(client=client_shop)
    client_shop.refresh_from_db()
    assert client_shop.api_enabled
    shown = client.get(reverse("dashboard:api-access"))
    raw = shown.context["raw_key"]
    assert raw.startswith(f"lgx_{key.prefix}_")
    assert raw in shown.content.decode()

    api = APIClient()
    api.credentials(HTTP_X_API_KEY=raw)
    response = api.post(
        "/api/v1/client/shipments/",
        {
            "pickup_address": {"city": "Tbilisi", "line1": "A 1"},
            "delivery_address": {"city": "Batumi", "line1": "B 2"},
            "recipient_name": "Nino",
            "recipient_phone": "+995555000111",
        },
        format="json",
    )
    assert response.status_code == 201

    client.post(reverse("dashboard:api-access"), {"intent": "revoke", "key_id": key.pk})
    key.refresh_from_db()
    assert not key.is_active
    denied = api.post(
        "/api/v1/client/shipments/",
        {
            "pickup_address": {"city": "Tbilisi", "line1": "A 1"},
            "delivery_address": {"city": "Batumi", "line1": "B 2"},
            "recipient_name": "Nino",
            "recipient_phone": "+995555000222",
        },
        format="json",
    )
    assert denied.status_code in {401, 403}
