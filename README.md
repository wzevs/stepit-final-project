# StepIT Final Project: Courier Platform

Logistics / courier service platform. Django + DRF backend, Android courier app,
and a browser site for shops, couriers, the company owner, and guests.

## Main site

Start the server, then open http://127.0.0.1:8000/.

This is the front door. It joins the pages that already exist:

- a service slider and the service list
- guest tracking by tracking number
- sign-in for a shop, a courier, and the courier-company owner

Shop staff land on /dashboard/shipments/. Couriers land on /courier/shipments/. Company members (owner, dispatcher, or viewer) land on /manage/shipments/. A wrong role or a bad password does not sign the user in. The public tracking result shows the status, the address, and the public event history. It does not show the recipient phone.


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

- Homepage: http://127.0.0.1:8000/
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

## Manager panel

Courier-company staff can also sign in at http://127.0.0.1:8000/manage/login/.
They need a CompanyMembership. Owners and dispatchers register shops and couriers and assign parcels.
Viewers can look, but cannot change anything.

## Courier list

After signing in, a courier sees their parcels at http://127.0.0.1:8000/courier/shipments/.
The list is read-only. Status changes and live location stay on the Android app.
