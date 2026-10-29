import pytest

from apps.accounts.models import User
from apps.clients.models import Client
from apps.companies.models import CourierCompany
from apps.core.models import Address
from apps.couriers.models import CourierProfile
from apps.shipments.models import Shipment


@pytest.fixture
def company(db):
    return CourierCompany.objects.create(name="Galaxy Express", slug="galaxy", tracking_prefix="GLX")


@pytest.fixture
def client_shop(company):
    return Client.objects.create(company=company, name="Shop One", code="SHOP1")


@pytest.fixture
def address(db):
    return Address.objects.create(city="Tbilisi", line1="Rustaveli 1", latitude=41.6971, longitude=44.7993)


@pytest.fixture
def shipment(company, client_shop, address):
    return Shipment.objects.create(
        company=company,
        client=client_shop,
        pickup_address=address,
        delivery_address=address,
        recipient_name="Nino",
        recipient_phone="+995555000000",
    )


@pytest.fixture
def courier_factory(company):
    def _make(*, email, company=company, **kwargs):
        user = User.objects.create_user(email=email, password="pass", role=User.Role.COURIER)
        return CourierProfile.objects.create(user=user, company=company, **kwargs)

    return _make


@pytest.fixture
def courier(courier_factory):
    return courier_factory(email="courier@example.com")
