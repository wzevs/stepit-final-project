import re
import secrets

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.clients.models import Client, ClientMembership, PickupPoint
from apps.companies.choice import ANY, company_choices, resolve_company
from apps.core.geo import require_coords
from apps.core.models import Address
from apps.network.models import District, Warehouse, WeightBand
from apps.shipments.creation import pickup_points_for
from apps.shipments.models import Shipment


class ShipmentCreateForm(forms.Form):
    external_id = forms.CharField(max_length=100, required=False, label="შეკვეთის ნომერი")
    pickup_point = forms.ModelChoiceField(
        queryset=PickupPoint.objects.none(), required=False, label="ფილიალი"
    )
    pickup_city = forms.CharField(max_length=100, required=False, label="აღება: ქალაქი")
    pickup_line1 = forms.CharField(max_length=255, required=False, label="აღება: მისამართი")
    pickup_lat = forms.DecimalField(
        max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput
    )
    pickup_lng = forms.DecimalField(
        max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput
    )
    delivery_city = forms.CharField(max_length=100, required=False, label="მიწოდება: ქალაქი")
    delivery_line1 = forms.CharField(max_length=255, required=False, label="მიწოდება: მისამართი")
    delivery_lat = forms.DecimalField(
        max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput
    )
    delivery_lng = forms.DecimalField(
        max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput
    )
    delivery_line2 = forms.CharField(max_length=255, required=False, label="სადარბაზო, სართული, ბინა")
    delivery_notes = forms.CharField(max_length=255, required=False, label="შენიშვნა კურიერისთვის")
    recipient_name = forms.CharField(max_length=150, label="მიმღები")
    recipient_phone = forms.CharField(max_length=20, label="ტელეფონი")
    recipient_email = forms.EmailField(required=False, label="ელფოსტა")
    description = forms.CharField(max_length=255, required=False, label="აღწერა")
    weight_kg = forms.DecimalField(
        max_digits=7, decimal_places=3, required=False, min_value=0, label="წონა (კგ)"
    )
    payment_type = forms.ChoiceField(
        choices=(
            (Shipment.PaymentType.PREPAID, "წინასწარ გადახდილი"),
            (Shipment.PaymentType.COD, "ნაღდი ადგილზე — მიმღები იხდის კურიერთან"),
        ),
        widget=forms.RadioSelect,
        initial=Shipment.PaymentType.PREPAID,
        label="გადახდა",
    )
    cod_amount = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, label="თანხა მიწოდებისას"
    )
    is_fragile = forms.BooleanField(required=False, label="მყიფე")
    origin_district = forms.ModelChoiceField(
        queryset=District.objects.none(), required=False, label="საიდან: უბანი"
    )
    destination_district = forms.ModelChoiceField(
        queryset=District.objects.none(), required=False, label="სად: უბანი"
    )
    home_delivery = forms.BooleanField(required=False, label="სახლამდე მიტანა")
    destination_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.none(), required=False, label="გატანა საწყობიდან"
    )
    pickup_window_start = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
        label="აღება — დან",
    )
    pickup_window_end = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
        label="აღება — მდე",
    )
    service_level = forms.ChoiceField(
        required=False,
        choices=(
            ("", "თარიღის გარეშე"),
            ("same_day", "დღეს"),
            ("next_day", "ხვალ"),
        ),
        label="მიწოდების დაპირება",
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="შენიშვნა")
    scheduled_delivery_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="მიწოდების თარიღი"
    )

    def __init__(self, *args, client, **kwargs):
        self.client = client
        super().__init__(*args, **kwargs)
        self.fields["pickup_point"].queryset = pickup_points_for(client)
        self.fields["pickup_point"].empty_label = "ფილიალის გარეშე, მისამართს ხელით"
        districts = District.objects.select_related("city").order_by("city__name", "name")
        self.fields["origin_district"].queryset = districts
        self.fields["destination_district"].queryset = districts
        self.fields["origin_district"].empty_label = "უბანი არ ვიცი"
        self.fields["destination_district"].empty_label = "უბანი არ ვიცი"
        warehouses = Warehouse.objects.filter(company=client.company, is_active=True).select_related(
            "city", "district"
        )
        self.fields["destination_warehouse"].queryset = warehouses
        self.fields["destination_warehouse"].empty_label = "საწყობი არა, მისამართზე"

    def clean(self):
        cleaned = super().clean()
        has_point = bool(cleaned.get("pickup_point"))
        has_pickup = bool(cleaned.get("pickup_city") and cleaned.get("pickup_line1"))
        if not has_point and not has_pickup:
            raise forms.ValidationError("აირჩიეთ აღების წერტილი ან მიუთითეთ აღების მისამართი.")
        if cleaned.get("payment_type") == Shipment.PaymentType.COD and not cleaned.get("cod_amount"):
            self.add_error("cod_amount", "თანხა აუცილებელია, როცა გადახდა მიწოდებისას ხდება.")
        warehouse = cleaned.get("destination_warehouse")
        home = bool(cleaned.get("home_delivery"))
        company_warehouses = self.fields["destination_warehouse"].queryset
        if home and warehouse is not None:
            self.add_error("destination_warehouse", "სახლამდე მიტანას საწყობი არ სჭირდება.")
        elif warehouse is None and not home and company_warehouses.exists():
            self.add_error("destination_warehouse", "აირჩიეთ საწყობი ან სახლამდე მიტანა.")
        dest = cleaned.get("destination_district")
        if warehouse is not None and dest is not None and warehouse.city_id != dest.city_id:
            self.add_error("destination_warehouse", "საწყობი დანიშნულების ქალაქში უნდა იყოს.")
        self._check_window(cleaned)
        try:
            if warehouse is None:
                if not cleaned.get("delivery_city") or not cleaned.get("delivery_line1"):
                    self.add_error("delivery_line1", "მიწოდების მისამართი აუცილებელია.")
                else:
                    require_coords(cleaned.get("delivery_lat"), cleaned.get("delivery_lng"))
            if has_pickup:
                require_coords(cleaned.get("pickup_lat"), cleaned.get("pickup_lng"))
            elif has_point and not cleaned["pickup_point"].address.is_geocoded:
                self.add_error(
                    "pickup_point",
                    "ამ წერტილს პინი არ აქვს. რუკაზე დასვით ან მისამართი ხელით მიუთითეთ.",
                )
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        weight = cleaned.get("weight_kg")
        bands = list(WeightBand.objects.filter(company=self.client.company))
        if bands and weight is None:
            self.add_error("weight_kg", "წონა აუცილებელია, რადგან ტარიფს წონის საფეხური აქვს.")
        elif bands and weight is not None and not any(band.covers(weight) for band in bands):
            self.add_error("weight_kg", "ამ წონის საფეხური არ არის.")
        return cleaned

    def _check_window(self, cleaned):
        start = cleaned.get("pickup_window_start")
        end = cleaned.get("pickup_window_end")
        point = cleaned.get("pickup_point")
        if (start is None) != (end is None):
            self.add_error("pickup_window_end", "აღების ინტერვალს ორივე დრო სჭირდება.")
            return
        if start is not None and end is not None and start >= end:
            self.add_error("pickup_window_end", "აღების დასასრული დასაწყისზე გვიან უნდა იყოს.")
            return
        if point is None or not point.opens_at or not point.closes_at:
            return
        if start is None:
            self.add_error("pickup_window_start", "ფილიალს საათები აქვს, აღების ინტერვალი აუცილებელია.")
            return
        if start < point.opens_at or end > point.closes_at:
            self.add_error("pickup_window_start", "აღების ინტერვალი ფილიალის საათებში უნდა ექცეოდეს.")

    def to_payload(self) -> dict:
        data = self.cleaned_data
        pickup = None
        if data.get("pickup_city") and data.get("pickup_line1"):
            pickup = {
                "city": data["pickup_city"],
                "line1": data["pickup_line1"],
                **require_coords(data.get("pickup_lat"), data.get("pickup_lng")),
            }
        warehouse = data.get("destination_warehouse")
        if warehouse is None:
            delivery = {
                "city": data["delivery_city"],
                "line1": data["delivery_line1"],
                "line2": data.get("delivery_line2") or "",
                "notes": data.get("delivery_notes") or "",
                **require_coords(data.get("delivery_lat"), data.get("delivery_lng")),
            }
        else:
            delivery = {
                "city": warehouse.address.city,
                "line1": warehouse.address.line1,
                "latitude": warehouse.address.latitude,
                "longitude": warehouse.address.longitude,
            }
        return {
            "external_id": data.get("external_id") or "",
            "pickup_point": data.get("pickup_point"),
            "pickup_address": pickup,
            "delivery_address": delivery,
            "destination_warehouse": warehouse,
            "recipient_name": data["recipient_name"],
            "recipient_phone": data["recipient_phone"],
            "recipient_email": data.get("recipient_email") or "",
            "description": data.get("description") or "",
            "weight_kg": data.get("weight_kg"),
            "payment_type": data["payment_type"],
            "cod_amount": data.get("cod_amount") or 0,
            "is_fragile": data.get("is_fragile") or False,
            "notes": data.get("notes") or "",
            "scheduled_delivery_date": data.get("scheduled_delivery_date"),
            "origin_district": data.get("origin_district"),
            "destination_district": data.get("destination_district"),
            "home_delivery": bool(data.get("home_delivery")) and warehouse is None,
            "pickup_window_start": data.get("pickup_window_start"),
            "pickup_window_end": data.get("pickup_window_end"),
            "service_level": data.get("service_level") or "",
        }


class BranchForm(forms.Form):
    name = forms.CharField(max_length=150, label="ფილიალის სახელი")
    district = forms.ModelChoiceField(queryset=District.objects.none(), label="უბანი")
    contact_phone = forms.CharField(max_length=20, required=False, label="ტელეფონი")
    line1 = forms.CharField(max_length=255, label="მისამართი")
    opens_at = forms.TimeField(
        required=False, widget=forms.TimeInput(attrs={"type": "time"}), label="იღებს — დან"
    )
    closes_at = forms.TimeField(
        required=False, widget=forms.TimeInput(attrs={"type": "time"}), label="იღებს — მდე"
    )
    latitude = forms.DecimalField(max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput)
    longitude = forms.DecimalField(max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput)
    is_default = forms.BooleanField(required=False, label="ძირითადი ფილიალი")

    def __init__(self, *args, shop, instance=None, **kwargs):
        self.shop = shop
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields["district"].queryset = District.objects.select_related("city").order_by(
            "city__name", "name"
        )

    def clean(self):
        cleaned = super().clean()
        opens = cleaned.get("opens_at")
        closes = cleaned.get("closes_at")
        if (opens is None) != (closes is None):
            self.add_error("closes_at", "საათები ორივე ერთად იწერება.")
        elif opens is not None and closes is not None and opens >= closes:
            self.add_error("closes_at", "დახურვა გახსნაზე გვიან უნდა იყოს.")
        try:
            require_coords(cleaned.get("latitude"), cleaned.get("longitude"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned

    def save(self) -> PickupPoint:
        data = self.cleaned_data
        coords = require_coords(data.get("latitude"), data.get("longitude"))
        with transaction.atomic():
            if data.get("is_default"):
                PickupPoint.objects.filter(client=self.shop, is_default=True).update(is_default=False)
            if self.instance is None:
                address = Address.objects.create(
                    city=data["district"].city.name, line1=data["line1"].strip(), **coords
                )
                return PickupPoint.objects.create(
                    client=self.shop,
                    name=data["name"].strip(),
                    district=data["district"],
                    address=address,
                    contact_phone=(data.get("contact_phone") or "").strip(),
                    opens_at=data.get("opens_at"),
                    closes_at=data.get("closes_at"),
                    is_default=bool(data.get("is_default")),
                )
            address = self.instance.address
            address.city = data["district"].city.name
            address.line1 = data["line1"].strip()
            address.latitude = coords["latitude"]
            address.longitude = coords["longitude"]
            address.save()
            self.instance.name = data["name"].strip()
            self.instance.district = data["district"]
            self.instance.contact_phone = (data.get("contact_phone") or "").strip()
            self.instance.opens_at = data.get("opens_at")
            self.instance.closes_at = data.get("closes_at")
            self.instance.is_default = bool(data.get("is_default"))
            self.instance.save()
            return self.instance


class ShopRegisterForm(forms.Form):
    """A shop opens its own account. The company still turns on API access."""

    company = forms.ChoiceField(
        required=False,
        label="საკურიერო კომპანია",
        help_text="სულ ერთია ნიშნავს: ავირჩევთ კომპანიას, რომელსაც ახლა თავისუფალი კურიერი ჰყავს.",
    )
    shop_name = forms.CharField(max_length=200, label="კლიენტის სახელი")
    contact_name = forms.CharField(max_length=150, label="საკონტაქტო პირი")
    email = forms.EmailField(label="ელფოსტა")
    phone = forms.CharField(max_length=20, label="ტელეფონი")
    password = forms.CharField(widget=forms.PasswordInput, label="პაროლი")
    password2 = forms.CharField(widget=forms.PasswordInput, label="პაროლი თავიდან")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].choices = company_choices()
        self.fields["company"].initial = ANY

    def clean_company(self):
        return resolve_company(self.cleaned_data.get("company") or ANY)

    def clean_shop_name(self):
        name = self.cleaned_data["shop_name"].strip()
        if not name:
            raise forms.ValidationError("სახელი აუცილებელია.")
        return name

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("ეს ელფოსტა უკვე რეგისტრირებულია.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password and password != cleaned.get("password2"):
            self.add_error("password2", "პაროლები არ ემთხვევა.")
        if password and cleaned.get("email"):
            candidate = User(email=cleaned["email"], first_name=(cleaned.get("contact_name") or "")[:150])
            try:
                validate_password(password, candidate)
            except ValidationError as exc:
                self.add_error("password", exc.messages)
        return cleaned

    def save(self):
        data = self.cleaned_data
        company = data["company"]
        contact = data["contact_name"].strip()
        parts = contact.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:])
        with transaction.atomic():
            user = User.objects.create_user(
                email=data["email"],
                password=data["password"],
                role=User.Role.CLIENT_STAFF,
                first_name=first_name,
                last_name=last_name,
                phone=data["phone"].strip(),
            )
            client = Client.objects.create(
                company=company,
                name=data["shop_name"],
                code=_shop_code(company, data["shop_name"]),
                contact_name=contact,
                contact_email=data["email"],
                contact_phone=data["phone"].strip(),
                api_enabled=False,
            )
            ClientMembership.objects.create(
                user=user, client=client, role=ClientMembership.Role.MANAGER
            )
        return user


def _shop_code(company, name: str) -> str:
    base = re.sub(r"[^A-Z0-9]", "", name.upper())[:20] or "SHOP"
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(8):
        suffix = "".join(secrets.choice(alphabet) for _ in range(4))
        code = f"{base}-{suffix}"[:30]
        if not Client.objects.filter(company=company, code=code).exists():
            return code
    raise forms.ValidationError("კოდი ვერ შეიქმნა. სცადეთ თავიდან.")
