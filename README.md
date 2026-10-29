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

## Shop access

Shops with their own software use POST /api/v1/client/shipments/ and the X-API-Key header.
Sending the same external_id again returns the existing shipment (HTTP 200) instead of a duplicate.
Interactive docs: http://127.0.0.1:8000/api/docs/

Shops without an integration sign in at http://127.0.0.1:8000/dashboard/login/ and add parcels by hand.
The dashboard account needs a ClientMembership; API access also requires Client.api_enabled.
