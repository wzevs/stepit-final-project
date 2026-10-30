import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import ClientMembership
from apps.companies.models import CompanyMembership
from apps.shipments.models import Shipment

pytestmark = pytest.mark.django_db


def test_home_links_the_three_logins_and_tracking(client):
    response = client.get(reverse("home"))
    body = response.content.decode()
    assert response.status_code == 200
    assert 'name="q"' in body
    assert 'value="shop"' in body
    assert 'value="courier"' in body
    assert 'value="owner"' in body


def test_guest_tracking_shows_status_but_not_the_phone(client, shipment):
    response = client.get(reverse("home"), {"q": shipment.tracking_number.lower()})
    body = response.content.decode()
    assert shipment.tracking_number in body
    assert "ელოდება აღებას" in body
    assert shipment.recipient_phone not in body


def test_unknown_tracking_number(client, db):
    response = client.get(reverse("home"), {"q": "GLX-NOSUCH1"})
    assert "ვერ მოიძებნა" in response.content.decode()


def test_shop_login_opens_the_shop_dashboard(client, client_shop):
    User.objects.create_user(email="shop@example.com", password="pass", role=User.Role.CLIENT_STAFF)
    user = User.objects.get(email="shop@example.com")
    ClientMembership.objects.create(user=user, client=client_shop, role=ClientMembership.Role.MANAGER)
    response = client.post(
        reverse("gate-login"),
        {"role": "shop", "username": "shop@example.com", "password": "pass"},
    )
    assert response.status_code == 302
    assert response.url == "/dashboard/shipments/"


def test_owner_login_opens_the_company_panel(client, company):
    user = User.objects.create_user(email="owner@example.com", password="pass", role=User.Role.COMPANY_STAFF)
    CompanyMembership.objects.create(user=user, company=company, role=CompanyMembership.Role.OWNER)
    response = client.post(
        reverse("gate-login"),
        {"role": "owner", "username": "owner@example.com", "password": "pass"},
    )
    assert response.status_code == 302
    assert response.url == "/manage/shipments/"


def test_courier_login_opens_only_their_shipments(client, courier, shipment):
    shipment.courier = courier
    shipment.status = Shipment.Status.ASSIGNED
    shipment.save(update_fields=["courier", "status"])
    response = client.post(
        reverse("gate-login"),
        {"role": "courier", "username": "courier@example.com", "password": "pass"},
    )
    assert response.status_code == 302
    assert response.url == "/courier/map/"
    page = client.get(response.url)
    assert 'id="map"' in page.content.decode()
    listed = client.get("/courier/shipments/")
    assert shipment.tracking_number in listed.content.decode()


def test_shop_user_cannot_enter_as_a_courier(client, client_shop):
    user = User.objects.create_user(email="shop@example.com", password="pass", role=User.Role.CLIENT_STAFF)
    ClientMembership.objects.create(user=user, client=client_shop)
    response = client.post(
        reverse("gate-login"),
        {"role": "courier", "username": "shop@example.com", "password": "pass"},
    )
    assert response.status_code == 302
    assert response.url == "/#login"
    assert "_auth_user_id" not in client.session


def test_wrong_password(client, db):
    response = client.post(
        reverse("gate-login"),
        {"role": "shop", "username": "missing@example.com", "password": "nope"},
    )
    assert response.status_code == 302
    assert response.url == "/#login"
