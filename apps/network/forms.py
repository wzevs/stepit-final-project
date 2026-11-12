from decimal import Decimal

from django import forms
from django.db import transaction

from apps.clients.models import Client
from apps.core.geo import require_coords
from apps.core.models import Address
from apps.network.models import City, District, Warehouse, WeightBand


class CityForm(forms.Form):
    name = forms.CharField(max_length=100, label="ქალაქი")

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if City.objects.filter(name__iexact=name).exists():
            raise forms.ValidationError("ეს ქალაქი უკვე არის.")
        return name

    def save(self) -> City:
        return City.objects.create(name=self.cleaned_data["name"])


class DistrictForm(forms.Form):
    city = forms.ModelChoiceField(queryset=City.objects.none(), label="ქალაქი")
    name = forms.CharField(max_length=100, label="უბანი")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["city"].queryset = City.objects.order_by("name")

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean(self):
        cleaned = super().clean()
        city = cleaned.get("city")
        name = cleaned.get("name")
        if city and name and District.objects.filter(city=city, name__iexact=name).exists():
            self.add_error("name", "ეს უბანი ამ ქალაქში უკვე არის.")
        return cleaned

    def save(self) -> District:
        return District.objects.create(city=self.cleaned_data["city"], name=self.cleaned_data["name"])


class WarehouseForm(forms.Form):
    name = forms.CharField(max_length=150, label="სახელი")
    kind = forms.ChoiceField(choices=Warehouse.Kind.choices, label="ტიპი")
    city = forms.ModelChoiceField(queryset=City.objects.none(), label="ქალაქი")
    district = forms.ModelChoiceField(queryset=District.objects.none(), required=False, label="უბანი")
    line1 = forms.CharField(max_length=255, label="მისამართი")
    latitude = forms.DecimalField(max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput)
    longitude = forms.DecimalField(max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput)
    is_active = forms.BooleanField(required=False, initial=True, label="აქტიური")

    def __init__(self, *args, company, instance=None, **kwargs):
        self.company = company
        self.instance = instance
        super().__init__(*args, **kwargs)
        self.fields["city"].queryset = City.objects.order_by("name")
        self.fields["district"].queryset = District.objects.select_related("city").order_by(
            "city__name", "name"
        )
        self.fields["district"].empty_label = "— უბანი არ სჭირდება —"

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        taken = Warehouse.objects.filter(company=self.company, name__iexact=name)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("ეს სახელი უკვე გამოყენებულია.")
        return name

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        city = cleaned.get("city")
        district = cleaned.get("district")
        if kind == Warehouse.Kind.CITY:
            cleaned["district"] = None
        elif kind == Warehouse.Kind.DISTRICT and district is None:
            self.add_error("district", "უბნის საწყობს უბანი სჭირდება.")
        elif district is not None and city is not None and district.city_id != city.id:
            self.add_error("district", "ეს უბანი არჩეულ ქალაქს არ ეკუთვნის.")
        try:
            require_coords(cleaned.get("latitude"), cleaned.get("longitude"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned

    def save(self) -> Warehouse:
        data = self.cleaned_data
        coords = require_coords(data.get("latitude"), data.get("longitude"))
        with transaction.atomic():
            if self.instance is None:
                address = Address.objects.create(
                    city=data["city"].name, line1=data["line1"].strip(), **coords
                )
                return Warehouse.objects.create(
                    company=self.company,
                    name=data["name"],
                    kind=data["kind"],
                    city=data["city"],
                    district=data.get("district"),
                    address=address,
                    is_active=bool(data.get("is_active")),
                )
            address = self.instance.address
            address.city = data["city"].name
            address.line1 = data["line1"].strip()
            address.latitude = coords["latitude"]
            address.longitude = coords["longitude"]
            address.save()
            self.instance.name = data["name"]
            self.instance.kind = data["kind"]
            self.instance.city = data["city"]
            self.instance.district = data.get("district")
            self.instance.is_active = bool(data.get("is_active"))
            self.instance.save()
            return self.instance


class WeightBandForm(forms.Form):
    min_kg = forms.DecimalField(max_digits=7, decimal_places=3, min_value=Decimal("0"), label="დან (კგ)")
    max_kg = forms.DecimalField(
        max_digits=7, decimal_places=3, required=False, label="მდე (კგ), ცარიელი ნიშნავს ზემოთ"
    )
    surcharge = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), label="დანამატი (₾)"
    )

    def __init__(self, *args, company, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        min_kg = cleaned.get("min_kg")
        max_kg = cleaned.get("max_kg")
        if min_kg is not None and max_kg is not None and max_kg <= min_kg:
            self.add_error("max_kg", "ზედა ზღვარი ქვედაზე მეტი უნდა იყოს.")
            return cleaned
        if min_kg is None:
            return cleaned
        clash = WeightBand.objects.filter(company=self.company)
        if any(band.overlaps(min_kg, max_kg) for band in clash):
            self.add_error("min_kg", "ეს შუალედი უკვე არსებულ საფეხურს ფარავს.")
        return cleaned

    def save(self):
        data = self.cleaned_data
        return WeightBand.objects.create(
            company=self.company,
            min_kg=data["min_kg"],
            max_kg=data.get("max_kg"),
            surcharge=data["surcharge"],
        )


class MoneyForm(forms.Form):
    price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), label="ფასი (₾)")


class CutoffForm(forms.Form):
    same_day_cutoff = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}), label="საჭრელი საათი"
    )


class ShopPriceForm(forms.Form):
    client = forms.ModelChoiceField(queryset=Client.objects.none(), label="მაღაზია")
    standard_price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        label="სტანდარტული ფასი (₾)",
    )

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(company=company, is_active=True).exclude(
            code="WALKIN"
        )


class CityTariffForm(MoneyForm):
    origin_city = forms.ModelChoiceField(queryset=City.objects.none(), label="საიდან")
    destination_city = forms.ModelChoiceField(queryset=City.objects.none(), label="სად")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cities = City.objects.order_by("name")
        self.fields["origin_city"].queryset = cities
        self.fields["destination_city"].queryset = cities


class DistrictTariffForm(MoneyForm):
    origin_district = forms.ModelChoiceField(queryset=District.objects.none(), label="საიდან")
    destination_district = forms.ModelChoiceField(queryset=District.objects.none(), label="სად")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        districts = District.objects.select_related("city").order_by("city__name", "name")
        self.fields["origin_district"].queryset = districts
        self.fields["destination_district"].queryset = districts


class QuoteTryForm(forms.Form):
    origin_district = forms.ModelChoiceField(queryset=District.objects.none(), label="საიდან")
    destination_district = forms.ModelChoiceField(queryset=District.objects.none(), label="სად")
    home_delivery = forms.BooleanField(required=False, label="სახლამდე მიტანა")
    weight_kg = forms.DecimalField(
        max_digits=7, decimal_places=3, required=False, min_value=Decimal("0"), label="წონა (კგ)"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        districts = District.objects.select_related("city").order_by("city__name", "name")
        self.fields["origin_district"].queryset = districts
        self.fields["destination_district"].queryset = districts
