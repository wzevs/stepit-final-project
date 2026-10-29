import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client, ClientMembership, PickupPoint
from apps.integrations.models import ApiKey
from apps.shipments.models import Shipment
from apps.shipments.services import assign_courier, transition

pytestmark = pytest.mark.django_db

PICKUP = {"city": "Tbilisi", "line1": "Chavchavadze 5"}
DELIVERY = {"city": "Tbilisi", "line1": "Rustaveli 10", "line2": "flat 4"}


@pytest.fixture
def api_key(client_shop):
    client_shop.api_enabled = True
    client_shop.save(update_fields=["api_enabled"])
    return ApiKey.issue(client_shop, "ERP")


@pytest.fixture
def api(api_key):
    _, raw = api_key
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=raw)
    return client


def _body(**extra):
    return {
        "pickup_address": PICKUP,
        "delivery_address": DELIVERY,
        "recipient_name": "Nino",
        "recipient_phone": "+995555000111",
        **extra,
    }


def test_missing_key_is_rejected():
    response = APIClient().post("/api/v1/client/shipments/", _body(), format="json")
    assert response.status_code == 401


def test_bad_key_is_unauthorized():
    client = APIClient()
    client.credentials(HTTP_X_API_KEY="lgx_nope_nope")
    response = client.post("/api/v1/client/shipments/", _body(), format="json")
    assert response.status_code == 401


def test_api_disabled_is_forbidden(client_shop):
    client_shop.api_enabled = False
    client_shop.save(update_fields=["api_enabled"])
    _, raw = ApiKey.issue(client_shop, "ERP")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=raw)
    response = client.post("/api/v1/client/shipments/", _body(), format="json")
    assert response.status_code == 403


def test_create_lists_and_retrieves(api):
    created = api.post("/api/v1/client/shipments/", _body(external_id="ORD-1"), format="json")
    assert created.status_code == 201
    assert created.data["tracking_number"].startswith("GLX-")
    assert created.data["status"] == Shipment.Status.PENDING
    assert created.data["source"] == Shipment.Source.API
    assert created.data["delivery_address"]["line2"] == "flat 4"

    listed = api.get("/api/v1/client/shipments/")
    assert listed.status_code == 200
    assert listed.data["count"] == 1

    detail = api.get(f"/api/v1/client/shipments/{created.data['id']}/")
    assert detail.status_code == 200
    assert detail.data["external_id"] == "ORD-1"


def test_repeat_external_id_returns_the_same_shipment(api):
    first = api.post(
        "/api/v1/client/shipments/", _body(external_id="ORD-1", recipient_name="Nino"), format="json"
    )
    second = api.post(
        "/api/v1/client/shipments/", _body(external_id="ORD-1", recipient_name="Other"), format="json"
    )
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert second.data["recipient_name"] == "Nino"
    assert Shipment.objects.count() == 1


def test_same_external_id_is_allowed_for_another_shop(api, company):
    api.post("/api/v1/client/shipments/", _body(external_id="ORD-1"), format="json")
    other = Client.objects.create(company=company, name="Shop Two", code="SHOP2", api_enabled=True)
    _, raw = ApiKey.issue(other, "ERP")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=raw)
    response = client.post("/api/v1/client/shipments/", _body(external_id="ORD-1"), format="json")
    assert response.status_code == 201
    assert Shipment.objects.count() == 2


def test_shop_cannot_see_another_shops_shipment(api, company):
    other = Client.objects.create(company=company, name="Shop Two", code="SHOP2", api_enabled=True)
    _, raw = ApiKey.issue(other, "ERP")
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=raw)
    created = client.post("/api/v1/client/shipments/", _body(), format="json")
    hidden = api.get(f"/api/v1/client/shipments/{created.data['id']}/")
    assert hidden.status_code == 404


def test_pickup_point_copies_its_address(api, client_shop, address):
    point = PickupPoint.objects.create(client=client_shop, name="Main", address=address, is_default=True)
    body = _body(pickup_point=str(point.pk))
    del body["pickup_address"]
    response = api.post("/api/v1/client/shipments/", body, format="json")
    assert response.status_code == 201
    shipment = Shipment.objects.get(pk=response.data["id"])
    assert shipment.pickup_point_id == point.pk
    assert shipment.pickup_address_id != address.pk
    assert shipment.pickup_address.line1 == address.line1


def test_pickup_point_of_another_shop_is_rejected(api, company, address):
    other = Client.objects.create(company=company, name="Shop Two", code="SHOP2")
    point = PickupPoint.objects.create(client=other, name="Theirs", address=address)
    response = api.post("/api/v1/client/shipments/", _body(pickup_point=point.pk), format="json")
    assert response.status_code == 400


def test_cod_requires_amount(api):
    response = api.post("/api/v1/client/shipments/", _body(payment_type="cod", cod_amount="0"), format="json")
    assert response.status_code == 400


def test_cancel_pending_shipment(api):
    created = api.post("/api/v1/client/shipments/", _body(), format="json")
    response = api.post(f"/api/v1/client/shipments/{created.data['id']}/cancel/")
    assert response.status_code == 200
    assert response.data["status"] == Shipment.Status.CANCELLED


def test_cannot_cancel_after_pickup(api, courier):
    created = api.post("/api/v1/client/shipments/", _body(), format="json")
    shipment = Shipment.objects.get(pk=created.data["id"])
    assign_courier(shipment, courier)
    transition(shipment, Shipment.Status.PICKED_UP)
    response = api.post(f"/api/v1/client/shipments/{shipment.pk}/cancel/")
    assert response.status_code == 409
    shipment.refresh_from_db()
    assert shipment.status == Shipment.Status.PICKED_UP


def test_key_records_last_use(api, api_key):
    key, _ = api_key
    assert key.last_used_at is None
    api.get("/api/v1/client/shipments/")
    key.refresh_from_db()
    assert key.last_used_at is not None


def test_schema_documents_the_client_api():
    response = APIClient().get("/api/schema/")
    assert response.status_code == 200
    body = response.content.decode()
    assert "/api/v1/client/shipments/" in body
    assert "X-API-Key" in body


def test_staff_user_can_create_without_an_api_key(client_shop):
    user = User.objects.create_user(email="shop@example.com", password="pass", role=User.Role.CLIENT_STAFF)
    ClientMembership.objects.create(user=user, client=client_shop)
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post("/api/v1/client/shipments/", _body(), format="json")
    assert response.status_code == 201
    assert Shipment.objects.get().created_by == user
