import json

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.clients.models import ClientMembership
from apps.shipments.models import Shipment
from apps.tracking.models import CourierLocation

pytestmark = pytest.mark.django_db


def test_map_page_is_the_courier_home(client, courier, shipment):
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
    body = page.content.decode()
    assert page.status_code == 200
    assert 'id="map"' in body
    assert "/api/v1/courier" in body
    listed = client.get("/courier/shipments/")
    assert shipment.tracking_number in listed.content.decode()


def test_map_page_is_public_html(client):
    response = client.get("/courier/map/")
    body = response.content.decode()
    assert response.status_code == 200
    assert 'id="gate-form"' in body
    assert "/api/v1/auth/token/" in body


def test_shop_user_can_open_map_html_but_not_the_api(client, client_shop):
    User.objects.create_user(email="shop@example.com", password="pass", role=User.Role.CLIENT_STAFF)
    user = User.objects.get(email="shop@example.com")
    ClientMembership.objects.create(user=user, client=client_shop)
    client.force_login(user)
    page = client.get("/courier/map/")
    assert page.status_code == 200
    denied = client.get("/api/v1/courier/me/")
    assert denied.status_code == 403


def test_browser_session_uses_the_same_courier_api(client, courier):
    client.force_login(courier.user)
    me = client.get("/api/v1/courier/me/")
    assert me.status_code == 200
    assert me.json()["email"] == "courier@example.com"

    ping = client.post(
        "/api/v1/courier/locations/",
        data=json.dumps(
            {
                "points": [
                    {
                        "lat": "41.715100",
                        "lng": "44.827100",
                        "accuracy": 10,
                        "recorded_at": "2026-10-31T00:00:00+04:00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    assert ping.status_code == 202
    assert ping.json()["accepted"] == 1
    assert CourierLocation.objects.filter(courier=courier).count() == 1
