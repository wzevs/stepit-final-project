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


def test_shop_saves_a_branch_and_the_parcel_price(client, shop_user, client_shop, company):
    from decimal import Decimal

    from apps.clients.models import PickupPoint
    from apps.network.models import City, District, Tariff

    city, _ = City.objects.get_or_create(name="თბილისი")
    vake, _ = District.objects.get_or_create(city=city, name="ვაკე")
    saburtalo, _ = District.objects.get_or_create(city=city, name="საბურთალო")
    Tariff.objects.create(company=company, kind=Tariff.Kind.STANDARD, price=Decimal("5"))
    Tariff.objects.create(
        company=company,
        kind=Tariff.Kind.DISTRICT,
        price=Decimal("4"),
        origin_district=vake,
        destination_district=saburtalo,
    )
    Tariff.objects.create(company=company, kind=Tariff.Kind.HOME, price=Decimal("2"))
    client.force_login(shop_user)
    response = client.post(
        reverse("dashboard:branch-create"),
        {
            "name": "ვაკის ფილიალი",
            "district": vake.pk,
            "line1": "ჭავჭავაძის 5",
            "latitude": "41.710000",
            "longitude": "44.770000",
            "is_default": "on",
        },
    )
    assert response.status_code == 302
    branch = PickupPoint.objects.get(client=client_shop)
    assert branch.district_id == vake.pk
    assert branch.is_default is True

    response = client.post(
        reverse("dashboard:shipment-create"),
        {
            "pickup_point": branch.pk,
            "delivery_city": "თბილისი",
            "delivery_line1": "ვაჟა-ფშაველას 10",
            "destination_district": saburtalo.pk,
            "home_delivery": "on",
            "recipient_name": "Nino",
            "recipient_phone": "+995555000333",
            "payment_type": "prepaid",
            "delivery_lat": "41.723000",
            "delivery_lng": "44.751000",
        },
    )
    shipment = Shipment.objects.get()
    assert response.status_code == 302
    assert shipment.shipping_fee == Decimal("6")
    assert shipment.tariff_basis == "district"
    assert shipment.home_fee == Decimal("2")
    page = client.get(
        reverse("dashboard:quote"),
        {"pickup_point": branch.pk, "destination": saburtalo.pk, "home": "1"},
    )
    assert page.json()["amount"] == "6.00"


def test_shop_must_give_a_weight_when_bands_exist(client, shop_user, company):
    from decimal import Decimal

    from apps.network.models import Tariff, WeightBand

    Tariff.objects.create(company=company, kind=Tariff.Kind.STANDARD, price=Decimal("5"))
    WeightBand.objects.create(company=company, min_kg=0, max_kg=5, surcharge=Decimal("2"))
    client.force_login(shop_user)
    missing = client.post(
        reverse("dashboard:shipment-create"),
        {
            "pickup_city": "Tbilisi",
            "pickup_line1": "Chavchavadze 5",
            "delivery_city": "Batumi",
            "delivery_line1": "Rustaveli 2",
            "recipient_name": "Nino",
            "recipient_phone": "+995555000444",
            "payment_type": "prepaid",
            **_PINS,
        },
    )
    assert missing.status_code == 200
    assert "წონა აუცილებელია" in missing.content.decode()
    assert not Shipment.objects.exists()


_REGISTER = {
    "shop_name": "ელიტი პლუს",
    "contact_name": "ანა კაპანაძე",
    "email": "newshop@example.com",
    "phone": "555100099",
    "password": "ShopPass2026",
    "password2": "ShopPass2026",
}


def test_shop_registers_and_lands_in_the_dashboard(client, company):
    response = client.post(reverse("shop-register"), _REGISTER)
    assert response.status_code == 302
    assert response.url == "/dashboard/shipments/"
    user = User.objects.get(email="newshop@example.com")
    assert user.role == User.Role.CLIENT_STAFF
    assert user.first_name == "ანა"
    membership = user.client_memberships.select_related("client").get()
    assert membership.role == ClientMembership.Role.MANAGER
    assert membership.client.company == company
    assert membership.client.name == "ელიტი პლუს"
    assert membership.client.api_enabled is False
    assert membership.client.code
    page = client.get("/dashboard/shipments/")
    assert page.status_code == 200
    assert "ელიტი პლუს" in page.content.decode()


def test_shop_register_rejects_a_duplicate_email(client, company):
    User.objects.create_user(email="newshop@example.com", password="ShopPass2026")
    response = client.post(reverse("shop-register"), _REGISTER)
    assert response.status_code == 200
    assert "უკვე რეგისტრირებულია" in response.content.decode()
    assert Client.objects.filter(name="ელიტი პლუს").count() == 0


def test_shop_register_needs_a_company(client):
    response = client.post(reverse("shop-register"), _REGISTER)
    assert response.status_code == 200
    assert "არ არის ხელმისაწვდომი" in response.content.decode()
    assert not User.objects.filter(email="newshop@example.com").exists()


def test_client_can_choose_the_courier_company(client, company):
    from apps.companies.models import CourierCompany

    other = CourierCompany.objects.create(name="Other Express", slug="other", tracking_prefix="OTH")
    response = client.post(reverse("shop-register"), {**_REGISTER, "company": str(other.pk)})
    assert response.status_code == 302
    membership = User.objects.get(email="newshop@example.com").client_memberships.get()
    assert membership.client.company_id == other.pk
    assert company.pk != other.pk
