# StepIT Final Project: Courier Platform

Logistics / courier service platform. Django + DRF backend, Android courier app,
and a browser site for shops, couriers, the company owner, and guests.

## Main site

Start the server, then open http://127.0.0.1:8000/.

This is the front door. It joins the pages that already exist:

- a service slider and the service list
- guest tracking by tracking number
- sign-in for a shop, a courier, and the courier-company owner

Shop staff land on /dashboard/shipments/. Couriers land on /courier/map/. Company members (owner, dispatcher, or viewer) land on /manage/shipments/. A wrong role or a bad password does not sign the user in. The public tracking result shows the status, the address, and the public event history. It does not show the recipient phone.


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

The live map is http://127.0.0.1:8000/manage/map/. It polls /manage/live/ every few seconds and moves the courier pin when a new GPS point arrives. This is polling, not WebSockets; that is enough to watch a courier during a delivery. Open it in a separate browser from the courier tabs so the session cookie is not overwritten. Recipient live tracking on a public link comes later.

## Courier map

Open http://127.0.0.1:8000/courier/map/ and sign in on the overlay. Each browser tab stores its own JWT, so three courier tabs can stay logged in at the same time. Do not use the homepage login for this demo: that cookie is shared across tabs and will overwrite the dispatcher.

Keep the dispatcher at http://127.0.0.1:8000/manage/map/ in another browser (or Incognito). The live map polls /manage/live/ every few seconds.

On a Windows browser, click the map to send a test location. On a phone, "ჩემი ადგილი" asks for GPS. Status buttons (picked up, out for delivery, delivered, failed) call POST /api/v1/courier/shipments/{id}/transition/. The old list is still at /courier/shipments/.

To try it from an Android browser on the same Wi-Fi:

```powershell
python manage.py runserver 0.0.0.0:8000
```

Then open http://<this-pc-ip>:8000/. Chrome on the phone often blocks GPS on plain HTTP; clicking the map still sends the point.

## Courier API

The Android app uses JWT, not the browser session.

1. POST /api/v1/auth/token/ with `{"email": "...", "password": "..."}`.
2. Send `Authorization: Bearer <access>` on every later call.
3. Refresh with POST /api/v1/auth/token/refresh/.

Courier endpoints:

- GET /api/v1/courier/me/
- POST /api/v1/courier/status/ with `{"status": "available"}` (or `busy` / `offline`)
- GET /api/v1/courier/shipments/
- POST /api/v1/courier/shipments/{id}/transition/ with `{"status": "picked_up"}`
- POST /api/v1/courier/locations/ with a `points` array
- POST /api/v1/courier/devices/ with the FCM token

A courier can pick up, mark in transit / out for delivery, deliver, or mark failed. Cancel and return stay on the manager panel. GPS points noisier than 200 m, or dated in the future, are dropped. Interactive docs: http://127.0.0.1:8000/api/docs/
