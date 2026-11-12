# Architecture

How a request becomes a row in PostgreSQL, and how the three cabinets stay apart.
ქართული ტექსტი ამავე ფაილის მეორე ნახევარშია.

## Request path

`config/urls.py` names the front door. A path points at a view. The view checks the role, reads a form or JSON, and calls a service. The service writes models. Django's ORM talks to the database named in `DATABASE_URL`.

```
browser or shop software
        │
        ▼
config/urls.py
        │
        ▼
view  (apps/core, apps/clients, apps/companies, apps/couriers, apps/api)
        │
        ▼
service  (shipments/services.py, shipments/creation.py, shipments/quote.py, notifications)
        │
        ▼
model  →  PostgreSQL
```

Settings module for local work is `config.settings.dev` (`manage.py`). If `DATABASE_URL` starts with `postgres://` or `postgresql://`, `dev.py` uses that database. Otherwise it falls back to SQLite.

## Tenants and roles

`CourierCompany` is the tenant. A shipment, a client, a courier, a warehouse, and a tariff all belong to one company.

| Who | Sign-in | What they hold |
| --- | --- | --- |
| Shop / client | Session cookie, `/login/` role `shop` | `ClientMembership` on one client |
| Dispatcher or owner | Session cookie, `/login/` role `owner` | `CompanyMembership` (`owner`, `dispatcher`, or `viewer`) |
| Courier | JWT in `sessionStorage`, `/courier/map/` | `CourierProfile` |
| Shop software | `X-API-Key` | A hash of the key, and `Client.api_enabled` |
| Guest | No account | The company's walk-in client, code `WALKIN` |

The courier map does not call Django `login()`, so a courier tab does not replace the dispatcher cookie. Open the dispatcher map in another browser or an Incognito window.

`User.username` is empty. Email is the login field. The password column stores a PBKDF2 hash. A tracking link stores only the SHA-256 of the raw token.

## Choosing a company

`apps/companies/choice.py` builds the dropdown and resolves the choice.

- A company id must be an active `CourierCompany`.
- Empty or `any` („სულ ერთია“) prefers an active company that has an active courier with status `available`, oldest first.
- If nobody is free, it uses the oldest active company.

Registration (`ShopRegisterForm`) creates the user, the client (`api_enabled` false), and a manager membership under that company. Guest send (`walk_in_client`) attaches the parcel to that company's „ფიზიკური პირები“ client.

## Price and status

`apps/shipments/quote.py` picks a price in this order: district pair, else city pair, else the shop's own standard tariff, else the company standard. A weight band is added (minimum inclusive, maximum exclusive). The home-delivery add-on applies only when the parcel goes to a door. Warehouse pickup skips it. The fees are copied onto the shipment.

Status changes go through `apps/shipments/services.py` `transition()`. Courier assignment uses `assign_courier` / `unassign_courier`. The legal statuses are `draft`, `pending`, `assigned`, `picked_up`, `in_transit`, `out_for_delivery`, `delivered`, `failed`, `returned`, `cancelled`.

## Database objects that are not Django models

PostgreSQL views, created in `apps/network` migrations:

- `network_tariff_sheet`
- `network_warehouse_sheet`
- `cod_open_sheet`

Triggers:

- `warehouse_district_city` — a district warehouse must sit in a district of its city
- `warehouse_same_company` — warehouse and district share a company
- `weightband_no_overlap` — weight bands do not overlap
- `shoptariff_same_company` — a shop tariff stays inside its company

The drawing with keys and join arrows is `presentation/schema.html`.

## Live position and messages

The dispatcher map opens a WebSocket at `/ws/manage/live/` (Channels / Daphne). If the socket drops, the page polls `/manage/live/`. The public recipient page `/t/<token>/` shows the courier pin only while the shipment is `out_for_delivery`.

Notifications are an outbox. `python manage.py process_outbox` sends queued SMS (uBill) and email (Gmail SMTP). Guest send delivers those messages immediately when the keys in `.env` are set.

---

# არქიტექტურა

მოთხოვნა ბრაუზერიდან ან მაღაზიის პროგრამიდან შედის `config/urls.py`-ში. მისამართი ირჩევს ხედს. ხედი ამოწმებს როლს, კითხულობს ფორმას ან JSON-ს და იძახებს სერვისს. სერვისი წერს მოდელს. მოდელი PostgreSQL-ს ელაპარაკება იმ მისამართით, რომელიც `.env`-ის `DATABASE_URL`-ში წერია. ამ კოდს კითხულობს `config/settings/dev.py`. თუ მისამართი ცარიელია, ლოკალური გაშვება SQLite-ზე გადადის.

```
ბრაუზერი ან მაღაზიის პროგრამა
        │
        ▼
config/urls.py
        │
        ▼
ხედი
        │
        ▼
სერვისი
        │
        ▼
მოდელი  →  PostgreSQL
```

## კომპანია და როლები

`CourierCompany` არის დამქირავებელი. ამანათი, კლიენტი, კურიერი, საწყობი და ტარიფი ერთ კომპანიას ეკუთვნის.

| ვინ | როგორ შედის | რა აქვს ბაზაში |
| --- | --- | --- |
| მაღაზია / კლიენტი | სესიის ქუქი, როლი `shop` | `ClientMembership` |
| დისპეჩერი ან მფლობელი | სესიის ქუქი, როლი `owner` | `CompanyMembership` |
| კურიერი | JWT ჩანართის `sessionStorage`-ში | `CourierProfile` |
| მაღაზიის პროგრამა | ჰედერი `X-API-Key` | გასაღების ჰეში და `Client.api_enabled` |
| სტუმარი | ანგარიშის გარეშე | კომპანიის კლიენტი კოდით `WALKIN` |

კურიერის რუკა Django-ს `login()`-ს არ იძახებს. ამიტომ კურიერის ჩანართი დისპეჩერის ქუქის არ შლის. დისპეჩერის რუკა გაიხსნას მეორე ბრაუზერში ან Incognito-ში.

მომხმარებელს `username` არ აქვს. შესვლა ელფოსტით ხდება. პაროლის სვეტში დევს PBKDF2 ჰეში, თავად პაროლი კი არა. ტრეკინგის ბმულის ნედლი ტოკენიც არ ინახება — მხოლოდ SHA-256.

## კომპანიის არჩევა

`apps/companies/choice.py` ავსებს სიას და წყვეტს არჩევანს.

- კონკრეტული იდენტიფიკატორი უნდა იყოს აქტიური კომპანია.
- ცარიელი მნიშვნელობა ან `any` („სულ ერთია“) ირჩევს აქტიურ კომპანიას, რომელსაც თავისუფალი კურიერი ჰყავს. რამდენიმეს შორის რჩება უძველესი.
- თუ თავისუფალი კურიერი არსად არის, რჩება უძველესი აქტიური კომპანია.

რეგისტრაცია ქმნის მომხმარებელს, კლიენტს (`api_enabled` გამორთული) და მენეჯერის წევრობას. სტუმრის გაგზავნა ამანათს აბავს იმ კომპანიის კლიენტზე „ფიზიკური პირები“.

## ფასი და სტატუსი

`apps/shipments/quote.py` ფასს ამ რიგით იღებს: უბნების წყვილი, მერე ქალაქების წყვილი, მერე მაღაზიის საკუთარი სტანდარტული, ბოლოს კომპანიის სტანდარტული. წონის დიაპაზონი ემატება (ქვედა ზღვარი შედის, ზედა არა). სახლამდე მიტანის დანამატი ერიცხება მხოლოდ კარზე მიტანისას. საწყობიდან გატანაზე არ ერიცხება. თანხა ამანათის ჩანაწერზე ინახება.

სტატუსს ცვლის მხოლოდ `apps/shipments/services.py`-ის `transition()`. კურიერის მიბმა და მოხსნა ცალკე ფუნქციებია. დასაშვები სტატუსებია: `draft`, `pending`, `assigned`, `picked_up`, `in_transit`, `out_for_delivery`, `delivered`, `failed`, `returned`, `cancelled`.

## ბაზის ობიექტები, რომლებიც Django-ს მოდელი არ არის

ხედები, შექმნილი `apps/network`-ის მიგრაციებში:

- `network_tariff_sheet`
- `network_warehouse_sheet`
- `cod_open_sheet`

ტრიგერები:

- `warehouse_district_city` — უბნის საწყობი უნდა იდგეს თავისი ქალაქის უბანში
- `warehouse_same_company` — საწყობი და უბანი ერთი კომპანიისაა
- `weightband_no_overlap` — წონის დიაპაზონები ერთმანეთს არ ფარავს
- `shoptariff_same_company` — მაღაზიის ტარიფი თავის კომპანიაში რჩება

ცხრილები, გასაღებები და შეერთების ისრები: `presentation/schema.html`.

## ცოცხალი წერტილი და შეტყობინება

დისპეჩერის რუკა იხსნის WebSocket-ს მისამართზე `/ws/manage/live/` (Channels და Daphne). კავშირის გაწყვეტისას გვერდი ეკითხება `/manage/live/`-ს. საჯარო გვერდი `/t/<token>/` კურიერის წერტილს აჩვენებს მხოლოდ მაშინ, როცა ამანათის სტატუსია `out_for_delivery`.

შეტყობინება ჯერ რიგში წერია. `python manage.py process_outbox` აგზავნის დაგროვილ SMS-ს (uBill) და ელფოსტას (Gmail SMTP). სტუმრის გაგზავნა წერილს მაშინვე გზავნის, თუ `.env`-ში გასაღებები შევსებულია.
