import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import ClientMembership
from apps.companies.models import CompanyMembership
from apps.shipments.models import Shipment

pytestmark = pytest.mark.django_db


def test_home_has_tracking_and_login_link_not_forms(client):
    response = client.get(reverse("home"))
    body = response.content.decode()
    assert response.status_code == 200
    assert 'name="q"' in body
    assert "Galaxy Express" in body
    assert 'href="/login/"' in body
    assert 'value="shop"' not in body
    assert 'value="owner"' not in body
    assert 'name="password"' not in body


def test_login_page_has_role_choice(client):
    response = client.get(reverse("gate-login"))
    body = response.content.decode()
    assert response.status_code == 200
    assert 'value="shop"' in body
    assert 'value="owner"' in body
    assert 'href="/courier/map/"' in body
    assert "მაღაზია" in body
    assert "კურიერი" in body
    assert "მფლობელი" in body


def test_guest_tracking_shows_status_but_not_the_phone(client, shipment):
    response = client.get(reverse("home"), {"q": shipment.tracking_number.lower()})
    body = response.content.decode()
    assert shipment.tracking_number in body
    assert "ელოდება აღებას" in body
    assert shipment.recipient_phone not in body
    assert "google.com/maps" not in body


def test_guest_tracking_hides_live_gps(client, shipment, courier):
    courier.last_latitude = 41.71
    courier.last_longitude = 44.79
    courier.save()
    shipment.courier = courier
    shipment.status = Shipment.Status.OUT_FOR_DELIVERY
    shipment.save(update_fields=["courier", "status"])
    body = client.get(reverse("home"), {"q": shipment.tracking_number}).content.decode()
    assert "google.com/maps" not in body
    assert "41.71" not in body


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


def test_courier_login_does_not_write_a_session(client, courier, shipment):
    shipment.courier = courier
    shipment.status = Shipment.Status.ASSIGNED
    shipment.save(update_fields=["courier", "status"])
    response = client.post(
        reverse("gate-login"),
        {"role": "courier", "username": "courier@example.com", "password": "pass"},
    )
    assert response.status_code == 302
    assert response.url == "/courier/map/"
    assert "_auth_user_id" not in client.session
    page = client.get(response.url)
    assert 'id="map"' in page.content.decode()
    listed = client.get("/courier/shipments/")
    assert listed.status_code == 302


def test_shop_user_cannot_enter_as_a_courier(client, client_shop):
    user = User.objects.create_user(email="shop@example.com", password="pass", role=User.Role.CLIENT_STAFF)
    ClientMembership.objects.create(user=user, client=client_shop)
    response = client.post(
        reverse("gate-login"),
        {"role": "courier", "username": "shop@example.com", "password": "pass"},
    )
    assert response.status_code == 302
    assert response.url.startswith("/login/")
    assert "_auth_user_id" not in client.session


def test_wrong_password(client, db):
    response = client.post(
        reverse("gate-login"),
        {"role": "shop", "username": "missing@example.com", "password": "nope"},
    )
    assert response.status_code == 302
    assert response.url == "/login/"
