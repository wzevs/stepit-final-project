from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import ClientMembership
from apps.couriers.models import Device
from apps.shipments.models import Shipment
from apps.shipments.services import assign_courier, transition
from apps.tracking.models import CourierLocation

pytestmark = pytest.mark.django_db

S = Shipment.Status


@pytest.fixture
def api(courier):
    client = APIClient()
    token = client.post(
        "/api/v1/auth/token/",
        {"email": "courier@example.com", "password": "pass"},
        format="json",
    )
    assert token.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.data['access']}")
    return client


def test_login_returns_jwt(courier):
    response = APIClient().post(
        "/api/v1/auth/token/",
        {"email": "courier@example.com", "password": "pass"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["access"]
    assert response.data["refresh"]


def test_shop_user_cannot_use_courier_api(client_shop):
    User.objects.create_user(email="shop@example.com", password="pass", role=User.Role.CLIENT_STAFF)
    user = User.objects.get(email="shop@example.com")
    ClientMembership.objects.create(user=user, client=client_shop)
    client = APIClient()
    token = client.post(
        "/api/v1/auth/token/",
        {"email": "shop@example.com", "password": "pass"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.data['access']}")
    response = client.get("/api/v1/courier/me/")
    assert response.status_code == 403


def test_me_and_status(api, courier):
    me = api.get("/api/v1/courier/me/")
    assert me.status_code == 200
    assert me.data["email"] == "courier@example.com"
    assert me.data["status"] == courier.status

    updated = api.post("/api/v1/courier/status/", {"status": "available"}, format="json")
    assert updated.status_code == 200
    assert updated.data["status"] == "available"
    courier.refresh_from_db()
    assert courier.status == "available"


def test_lists_only_this_couriers_parcels(
    api, courier, courier_factory, shipment, company, client_shop, address
):
    assign_courier(shipment, courier)
    other = courier_factory(email="other@example.com")
    theirs = Shipment.objects.create(
        company=company,
        client=client_shop,
        courier=other,
        pickup_address=address,
        delivery_address=address,
        recipient_name="Gio",
        recipient_phone="+995555000222",
        status=S.ASSIGNED,
    )
    listed = api.get("/api/v1/courier/shipments/")
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.data["results"]}
    assert str(shipment.pk) in ids
    assert str(theirs.pk) not in ids

    hidden = api.get(f"/api/v1/courier/shipments/{theirs.pk}/")
    assert hidden.status_code == 404


def test_transition_picked_up_and_delivered(api, courier, shipment):
    assign_courier(shipment, courier)
    picked = api.post(
        f"/api/v1/courier/shipments/{shipment.pk}/transition/",
        {"status": "picked_up"},
        format="json",
    )
    assert picked.status_code == 200
    assert picked.data["status"] == S.PICKED_UP
    assert "picked_up" not in picked.data["allowed_next"]

    out = api.post(
        f"/api/v1/courier/shipments/{shipment.pk}/transition/",
        {"status": "out_for_delivery"},
        format="json",
    )
    assert out.status_code == 200

    done = api.post(
        f"/api/v1/courier/shipments/{shipment.pk}/transition/",
        {"status": "delivered", "received_by": "Nino"},
        format="json",
    )
    assert done.status_code == 200
    assert done.data["status"] == S.DELIVERED
    shipment.refresh_from_db()
    assert shipment.received_by == "Nino"
    assert shipment.delivered_at is not None


def test_failed_without_reason_is_rejected(api, courier, shipment):
    assign_courier(shipment, courier)
    transition(shipment, S.PICKED_UP)
    transition(shipment, S.OUT_FOR_DELIVERY)
    response = api.post(
        f"/api/v1/courier/shipments/{shipment.pk}/transition/",
        {"status": "failed"},
        format="json",
    )
    assert response.status_code == 400


def test_courier_cannot_cancel(api, courier, shipment):
    assign_courier(shipment, courier)
    response = api.post(
        f"/api/v1/courier/shipments/{shipment.pk}/transition/",
        {"status": "cancelled"},
        format="json",
    )
    assert response.status_code == 400


def test_locations_keep_good_points_and_drop_noise(api, courier):
    now = timezone.now()
    response = api.post(
        "/api/v1/courier/locations/",
        {
            "points": [
                {
                    "lat": "41.715100",
                    "lng": "44.827100",
                    "accuracy": 12.5,
                    "recorded_at": now.isoformat(),
                },
                {
                    "lat": "41.716000",
                    "lng": "44.828000",
                    "accuracy": 500,
                    "recorded_at": now.isoformat(),
                },
                {
                    "lat": "41.717000",
                    "lng": "44.829000",
                    "accuracy": 8,
                    "recorded_at": (now + timedelta(hours=1)).isoformat(),
                },
            ]
        },
        format="json",
    )
    assert response.status_code == 202
    assert response.data["accepted"] == 1
    assert CourierLocation.objects.filter(courier=courier).count() == 1
    courier.refresh_from_db()
    assert courier.last_latitude == Decimal("41.715100")
    assert courier.last_location_at is not None


def test_device_register_updates_same_tablet(api, courier):
    first = api.post(
        "/api/v1/courier/devices/",
        {"fcm_token": "token-1", "device_id": "tablet-9", "model_name": "Lenovo Tab"},
        format="json",
    )
    assert first.status_code == 200
    second = api.post(
        "/api/v1/courier/devices/",
        {"fcm_token": "token-2", "device_id": "tablet-9", "app_version": "1.0.1"},
        format="json",
    )
    assert second.status_code == 200
    assert Device.objects.filter(courier=courier).count() == 1
    device = Device.objects.get(courier=courier)
    assert device.fcm_token == "token-2"
    assert device.app_version == "1.0.1"
    assert device.last_seen_at is not None
