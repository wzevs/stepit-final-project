import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import ClientMembership
from apps.companies.models import CompanyMembership
from apps.couriers.models import CourierProfile
from apps.notifications.models import Notification
from apps.shipments.models import Shipment
from apps.tracking.models import TrackingToken
from apps.tracking.services import public_live_payload

pytestmark = pytest.mark.django_db


def test_home_has_tracking_and_login_link_not_forms(client):
    response = client.get(reverse("home"))
    body = response.content.decode()
    assert response.status_code == 200
    assert 'name="q"' in body
    assert "Galaxy Express" in body
    assert "როგორ მუშაობს" in body
    assert "რას გთავაზობთ" in body
    assert "გაბარიტული" in body
    assert 'href="/send/"' in body
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


def test_guest_send_page_needs_no_login(client):
    response = client.get(reverse("guest-send"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "ანგარიში არ სჭირდება" in body
    assert 'id="pickup-map"' in body
    assert 'id="delivery-map"' in body


_GUEST_SEND = {
    "sender_name": "Giorgi",
    "sender_phone": "555111222",
    "sender_email": "giorgi@example.com",
    "pickup_city": "Tbilisi",
    "pickup_line1": "Rustaveli 1",
    "pickup_lat": "41.701111",
    "pickup_lng": "44.801111",
    "recipient_name": "Nino",
    "recipient_phone": "555000111",
    "recipient_email": "nino@example.com",
    "delivery_city": "Batumi",
    "delivery_line1": "Gorgasali 5",
    "delivery_lat": "41.616800",
    "delivery_lng": "41.636700",
}


def test_guest_send_requires_emails(client, company):
    payload = dict(_GUEST_SEND)
    payload.pop("sender_email")
    payload.pop("recipient_email")
    response = client.post(reverse("guest-send"), payload)
    assert response.status_code == 200
    assert Shipment.objects.count() == 0
    assert "ელფოსტა" in response.content.decode()


def test_guest_send_requires_pins(client, company):
    payload = dict(_GUEST_SEND)
    payload.pop("pickup_lat")
    payload.pop("pickup_lng")
    payload.pop("delivery_lat")
    payload.pop("delivery_lng")
    response = client.post(reverse("guest-send"), payload)
    assert response.status_code == 200
    assert Shipment.objects.count() == 0
    assert "პინი" in response.content.decode()


def test_guest_send_keeps_map_pin(client, company):
    response = client.post(
        reverse("guest-send"),
        _GUEST_SEND,
    )
    assert response.status_code == 302
    shipment = Shipment.objects.select_related("pickup_address", "delivery_address").get()
    assert str(shipment.pickup_address.latitude) == "41.701111"
    assert str(shipment.delivery_address.longitude) == "41.636700"


def test_guest_can_send_without_an_account(client, company):
    response = client.post(reverse("guest-send"), _GUEST_SEND)
    assert response.status_code == 302
    shipment = Shipment.objects.get()
    assert shipment.client.code == "WALKIN"
    assert shipment.client.company_id == company.pk
    assert shipment.recipient_name == "Nino"
    assert shipment.recipient_email == "nino@example.com"
    assert shipment.metadata["sender_email"] == "giorgi@example.com"
    assert shipment.courier_id is None
    page = client.get(response.url)
    body = page.content.decode()
    assert shipment.tracking_number in body
    assert "თქვენი რუკა" in body
    assert "მიმღების რუკა" in body
    assert TrackingToken.objects.filter(shipment=shipment, sent_via="sender").exists()
    assert TrackingToken.objects.filter(shipment=shipment, sent_via="recipient").exists()
    channels = set(Notification.objects.filter(shipment=shipment).values_list("channel", flat=True))
    assert channels == {Notification.Channel.EMAIL, Notification.Channel.SMS}
    assert {m.to[0] for m in mail.outbox} == {"giorgi@example.com", "nino@example.com"}
    assert all("/t/" in m.body for m in mail.outbox)


def test_guest_send_binds_available_courier_and_opens_live_map(client, company, courier_factory):
    courier = courier_factory(email="on@example.com", status=CourierProfile.Status.AVAILABLE)
    courier.last_latitude = 41.71
    courier.last_longitude = 44.79
    courier.last_location_at = timezone.now()
    courier.save()
    response = client.post(reverse("guest-send"), _GUEST_SEND)
    shipment = Shipment.objects.select_related("client", "courier", "pickup_address").get()
    assert shipment.courier_id == courier.pk
    assert shipment.status == Shipment.Status.ASSIGNED
    assert shipment.is_live_trackable
    page = client.get(response.url)
    assert "კურიერი მიბმულია" in page.content.decode()
    payload = public_live_payload(shipment)
    assert payload["live"] is True
    assert payload["courier"]["latitude"] == 41.71
    assert payload["pickup"]["city"] == "Tbilisi"
    assert Notification.objects.filter(
        shipment=shipment, template="walk_in_created", channel=Notification.Channel.EMAIL
    ).exists()
    assert Notification.objects.filter(
        shipment=shipment, template="walk_in_sender", channel=Notification.Channel.EMAIL
    ).exists()
    assert Notification.objects.filter(shipment=shipment, channel=Notification.Channel.SMS).count() == 2


def test_wrong_password(client, db):
    response = client.post(
        reverse("gate-login"),
        {"role": "shop", "username": "missing@example.com", "password": "nope"},
    )
    assert response.status_code == 302
    assert response.url == "/login/"
