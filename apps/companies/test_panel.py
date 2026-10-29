import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import Client
from apps.companies.models import CompanyMembership
from apps.couriers.models import CourierProfile
from apps.shipments.models import Shipment

pytestmark = pytest.mark.django_db


def _member(company, email, role):
    user = User.objects.create_user(email=email, password="manager-pass-1", role=User.Role.COMPANY_STAFF)
    CompanyMembership.objects.create(user=user, company=company, role=role)
    return user


@pytest.fixture
def manager(company):
    return _member(company, "manager@example.com", CompanyMembership.Role.DISPATCHER)


@pytest.fixture
def viewer(company):
    return _member(company, "viewer@example.com", CompanyMembership.Role.VIEWER)


def test_login_shows_shipments(client, manager, shipment):
    assert client.login(username="manager@example.com", password="manager-pass-1")
    response = client.get(reverse("manage:shipment-list"))
    assert response.status_code == 200
    assert shipment.tracking_number in response.content.decode()


def test_shop_user_cannot_open_the_panel(client, company):
    user = User.objects.create_user(email="shop@example.com", password="manager-pass-1")
    client.force_login(user)
    response = client.get(reverse("manage:shipment-list"))
    assert response.status_code == 403


def test_dispatcher_assigns_and_unassigns(client, manager, shipment, courier):
    client.force_login(manager)
    url = reverse("manage:shipment-detail", args=[shipment.pk])
    assigned = client.post(url, {"courier_id": str(courier.pk)})
    assert assigned.status_code == 302
    shipment.refresh_from_db()
    assert shipment.status == Shipment.Status.ASSIGNED
    assert shipment.courier_id == courier.pk

    cleared = client.post(url, {"courier_id": ""})
    assert cleared.status_code == 302
    shipment.refresh_from_db()
    assert shipment.status == Shipment.Status.PENDING
    assert shipment.courier_id is None


def test_viewer_cannot_assign(client, viewer, shipment, courier):
    client.force_login(viewer)
    response = client.post(
        reverse("manage:shipment-detail", args=[shipment.pk]), {"courier_id": str(courier.pk)}
    )
    assert response.status_code == 403
    shipment.refresh_from_db()
    assert shipment.courier_id is None


def test_other_company_shipment_is_hidden(client, manager, company, address):
    from apps.companies.models import CourierCompany

    other = CourierCompany.objects.create(name="Other", slug="other", tracking_prefix="OTH")
    shop = Client.objects.create(company=other, name="Other shop", code="OTH1")
    foreign = Shipment.objects.create(
        company=other,
        client=shop,
        pickup_address=address,
        delivery_address=address,
        recipient_name="A",
        recipient_phone="1",
    )
    client.force_login(manager)
    response = client.get(reverse("manage:shipment-detail", args=[foreign.pk]))
    assert response.status_code == 404


def test_dispatcher_registers_a_shop(client, manager, company):
    client.force_login(manager)
    response = client.post(
        reverse("manage:client-create"),
        {"name": "Shop Two", "code": "shop2", "contact_phone": "555", "api_enabled": "on"},
    )
    assert response.status_code == 302
    shop = Client.objects.get(company=company, code="SHOP2")
    assert shop.api_enabled is True


def test_dispatcher_registers_a_courier(client, manager, company):
    client.force_login(manager)
    response = client.post(
        reverse("manage:courier-create"),
        {
            "first_name": "Giorgi",
            "last_name": "Beridze",
            "email": "giorgi@example.com",
            "password": "courier-pass-1",
            "password2": "courier-pass-1",
            "vehicle_type": "moto",
            "vehicle_plate": "AA123BB",
        },
    )
    assert response.status_code == 302
    profile = CourierProfile.objects.get(user__email="giorgi@example.com")
    assert profile.company_id == company.pk
    assert profile.vehicle_type == "moto"
    assert profile.user.role == User.Role.COURIER
