from django import forms
from django.db import transaction

from apps.clients.models import PickupPoint
from apps.core.geo import require_coords
from apps.core.models import Address
from apps.network.models import District, WeightBand
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
    delivery_city = forms.CharField(max_length=100, label="მიწოდება: ქალაქი")
    delivery_line1 = forms.CharField(max_length=255, label="მიწოდება: მისამართი")
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

    def clean(self):
        cleaned = super().clean()
        has_point = bool(cleaned.get("pickup_point"))
        has_pickup = bool(cleaned.get("pickup_city") and cleaned.get("pickup_line1"))
        if not has_point and not has_pickup:
            raise forms.ValidationError("აირჩიეთ აღების წერტილი ან მიუთითეთ აღების მისამართი.")
        if cleaned.get("payment_type") == Shipment.PaymentType.COD and not cleaned.get("cod_amount"):
            self.add_error("cod_amount", "თანხა აუცილებელია, როცა გადახდა მიწოდებისას ხდება.")
        try:
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

    def to_payload(self) -> dict:
        data = self.cleaned_data
        pickup = None
        if data.get("pickup_city") and data.get("pickup_line1"):
            pickup = {
                "city": data["pickup_city"],
                "line1": data["pickup_line1"],
                **require_coords(data.get("pickup_lat"), data.get("pickup_lng")),
            }
        return {
            "external_id": data.get("external_id") or "",
            "pickup_point": data.get("pickup_point"),
            "pickup_address": pickup,
            "delivery_address": {
                "city": data["delivery_city"],
                "line1": data["delivery_line1"],
                "line2": data.get("delivery_line2") or "",
                "notes": data.get("delivery_notes") or "",
                **require_coords(data.get("delivery_lat"), data.get("delivery_lng")),
            },
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
            "home_delivery": bool(data.get("home_delivery")),
        }


class BranchForm(forms.Form):
    name = forms.CharField(max_length=150, label="ფილიალის სახელი")
    district = forms.ModelChoiceField(queryset=District.objects.none(), label="უბანი")
    contact_phone = forms.CharField(max_length=20, required=False, label="ტელეფონი")
    line1 = forms.CharField(max_length=255, label="მისამართი")
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
            self.instance.is_default = bool(data.get("is_default"))
            self.instance.save()
            return self.instance
