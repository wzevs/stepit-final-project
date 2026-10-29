# StepIT Final Project: Courier Platform

Logistics / courier service platform. Django + DRF backend, Android courier app,
browser-based tracking page for recipients.

## Stack

- Python 3.13, Django 5.2, Django REST Framework
- SQLite for local development, PostgreSQL in production
- JWT (SimpleJWT) for staff / courier auth, API keys for client integrations
- Google Maps for addresses and live tracking

## Project layout

```
config/            settings (base / dev / prod), urls, wsgi, asgi
apps/
  core/            TimeStampedModel, UUIDModel, Address
  accounts/        custom User (email login, role)
  companies/       CourierCompany (tenant), CompanyMembership
  clients/         Client (shop / warehouse), PickupPoint, ClientMembership
  couriers/        CourierProfile, Device (FCM tokens)
  shipments/       Shipment, ShipmentEvent
  tracking/        CourierLocation, TrackingToken
  integrations/    ApiKey, Webhook, WebhookDelivery
  notifications/   Notification outbox (SMS / Telegram / Email)
```

## Local setup

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Admin: http://127.0.0.1:8000/admin/
- API docs: http://127.0.0.1:8000/api/docs/

## Checks

```powershell
ruff check .
pytest
```
