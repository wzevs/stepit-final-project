# StepIT Final Project: Courier Platform

Logistics / courier service platform. Django + DRF backend, Android courier app,
and a browser site for shops, couriers, the company owner, and guests.

Contact channels are **phone (uBill SMS)** and **email (Gmail)**. Telegram was
replaced by Gmail and is not in the code.

## Scope

**Done**

- Public site: track by number, person-to-person send (`/send/`), role login
- Guest C2C: auto-assign a courier, live map links for sender and recipient
- Shop dashboard (manual parcels, branches, API keys) and shop HTTP API (`X-API-Key`)
- Company panel: shops, couriers, city and district warehouses, tariffs, assign / cancel / return, live dispatcher map
- Courier map in the browser (`/courier/map/`) over JWT
- Notifications: Gmail SMTP + uBill SMS to sender and recipient
- Outbox worker: `process_outbox`
- Street geocoding via Nominatim on shop API orders that omit a pin; a miss leaves coords empty until a manager or courier drops one
- Live maps over WebSocket, with HTTP polling as fallback
- Shop COD (cash with the courier); guest `/send/` stays prepaid
- Guest send, shop form, and shop default pickup require a map pin; shop API may omit coords and fall back to Nominatim
- Shipping price: district pair, else city pair, else the standard tariff, then a weight-band add-on, then home delivery. The amount is copied onto the shipment.

**Still in scope (not finished)**

- Native Android courier app (JWT API and FCM device endpoint already exist)

**Out**

- Telegram

## Main site

Start the server, then open http://127.0.0.1:8000/.

This is the front door. It joins the pages that already exist:

- a GLS-style header, photo slider, and footer
- guest tracking by tracking number on the homepage
- Login in the header, which opens /login/ for shop, courier, or company staff

Shop staff land on /dashboard/shipments/. Couriers land on /courier/map/. Company members (owner, dispatcher, or viewer) land on /manage/shipments/. A wrong role or a bad password does not sign the user in. The public tracking result shows the status, the address, and the public event history. It does not show the recipient phone or the courier GPS.

A recipient SMS/email link opens http://127.0.0.1:8000/t/<token>/. That page is the same public snapshot, plus a live map while the parcel is out for delivery. The raw token is not stored; a dead, expired, or unknown link returns 404.


## Stack

- Python 3.13, Django 5.2, Django REST Framework
- SQLite for a machine without PostgreSQL. Local development and the defense use PostgreSQL (`DATABASE_URL`).
- JWT (SimpleJWT) for staff / courier auth, API keys for client integrations
- Leaflet maps (Esri / CARTO tiles). Forms require a pin; only the shop API geocodes by street name.

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
  network/         City, District, Warehouse, Tariff
  integrations/    ApiKey, Webhook, WebhookDelivery
  notifications/   Notification outbox (SMS / Email)
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

Queued SMS/email and shop webhooks sit in the database until you drain them:

```powershell
python manage.py process_outbox
```

Guest send emails go out immediately over SMTP when `.env` has `EMAIL_HOST`, `EMAIL_HOST_USER`, and `EMAIL_HOST_PASSWORD` (Gmail app password on port 587). Without those keys, Django prints the message to the runserver console instead of a mailbox. Check the wiring with:

```powershell
python manage.py send_test_email you@gmail.com
```

SMS goes out through uBill when `.env` has `UBILL_API_KEY` and `UBILL_BRAND_ID` (the numeric id of an approved sender name, not the word `test`). Without those keys, Django prints SMS to the console. Check the wiring with:

```powershell
python manage.py send_test_sms 555123456
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
On `pickup_address` / `delivery_address` you can send `latitude` and `longitude`; those pins skip geocoding. This is the only create path that may omit a pin: Nominatim then looks up the street, and a miss leaves coordinates empty.
Interactive docs: http://127.0.0.1:8000/api/docs/

Shops without an integration sign in at http://127.0.0.1:8000/dashboard/login/ and add parcels by hand.
The dashboard account needs a ClientMembership; API access also requires Client.api_enabled.
From a shipment page the shop can cancel (before pickup), print a label, and copy a recipient tracking link.
Branches live at http://127.0.0.1:8000/dashboard/branches/. Each branch has a district. A new parcel picked from that branch is priced from the district, then the city, then the standard tariff. Home delivery is an add-on. The price is stored on the shipment.

## Manager panel

Courier-company staff can also sign in at http://127.0.0.1:8000/manage/login/.
They need a CompanyMembership. Owners and dispatchers register shops (optional default pickup point — with a required map pin) and couriers, assign parcels, cancel, or return to sender. On a shipment they can drop a map pin when a shop API address was not geocoded.
Viewers can look, but cannot change anything. "მიმღების ლინკი" mints a /t/<token>/ URL without sending SMS.

Warehouses are http://127.0.0.1:8000/manage/warehouses/. A city warehouse has no district. A district warehouse must sit in a district of that same city; on PostgreSQL a trigger rejects a mismatch. Cities and districts are http://127.0.0.1:8000/manage/places/. `python manage.py seed_places` loads the main Georgian cities (the first migrate does this too).

Tariffs are http://127.0.0.1:8000/manage/tariffs/. One standard price and one home-delivery add-on per company. City pairs and district pairs are separate rows. The page can calculate a sample route. Two SQL views, `network_tariff_sheet` and `network_warehouse_sheet`, join those tables for the defense.

Table drawings for the presentation are in `presentation/tables.html`. Open that file in a browser.

The live map is http://127.0.0.1:8000/manage/map/. It opens a WebSocket at /ws/manage/live/ and moves the pin when a GPS point arrives. If the socket drops, it falls back to polling /manage/live/. Open it in a separate browser from the courier tabs so the session cookie is not overwritten.

Recipient live tracking is the public page /t/<token>/. It polls /t/<token>/live/ and shows the courier pin only in out_for_delivery. Delivery address is always on the map when it is geocoded. Courier name, email, and the recipient phone stay off that page.

## Courier map

Open http://127.0.0.1:8000/courier/map/ and sign in on the overlay. Each browser tab stores its own JWT, so three courier tabs can stay logged in at the same time. The homepage does not create a courier session cookie, so the dispatcher map in another tab stays signed in.

Keep the dispatcher at http://127.0.0.1:8000/manage/map/ in another browser (or Incognito). The live map polls /manage/live/ every few seconds.

On a Windows browser, click the map to send a test location. On a phone, "ჩემი ადგილი" asks for GPS. Status buttons (picked up, out for delivery, delivered, failed) call POST /api/v1/courier/shipments/{id}/transition/. "დააზუსტე აღება/მიწოდება" then a map click calls POST /api/v1/courier/shipments/{id}/pin/. The old list is still at /courier/shipments/.

To try it from an Android browser on the same Wi-Fi:

```powershell
python manage.py runserver 0.0.0.0:8000
```

Then open http://<this-pc-ip>:8000/. Chrome on the phone often blocks GPS on plain HTTP; clicking the map still sends the point.

## Courier API

The Android app uses JWT, not the browser session. The same API already drives the browser courier map.

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
