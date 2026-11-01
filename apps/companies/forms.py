from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.clients.models import Client, PickupPoint
from apps.core.geo import city_center
from apps.core.models import Address
from apps.couriers.models import CourierProfile


class ClientCreateForm(forms.Form):
    name = forms.CharField(max_length=200, label="სახელი")
    code = forms.CharField(max_length=30, label="კოდი")
    contact_name = forms.CharField(max_length=150, required=False, label="საკონტაქტო პირი")
    contact_phone = forms.CharField(max_length=20, required=False, label="ტელეფონი")
    contact_email = forms.EmailField(required=False, label="ელფოსტა")
    api_enabled = forms.BooleanField(required=False, label="API წვდომა")
    pickup_city = forms.CharField(max_length=100, required=False, label="აღება: ქალაქი")
    pickup_line1 = forms.CharField(max_length=255, required=False, label="აღება: მისამართი")

    def __init__(self, *args, company, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if Client.objects.filter(company=self.company, code=code).exists():
            raise forms.ValidationError("ეს კოდი უკვე გამოყენებულია.")
        return code

    def clean(self):
        cleaned = super().clean()
        city = (cleaned.get("pickup_city") or "").strip()
        line1 = (cleaned.get("pickup_line1") or "").strip()
        if (city and not line1) or (line1 and not city):
            raise forms.ValidationError("აღების ქალაქი და მისამართი ერთად შეავსეთ.")
        return cleaned

    def save(self):
        data = self.cleaned_data
        client = Client.objects.create(
            company=self.company,
            name=data["name"].strip(),
            code=data["code"],
            contact_name=(data.get("contact_name") or "").strip(),
            contact_phone=(data.get("contact_phone") or "").strip(),
            contact_email=(data.get("contact_email") or "").strip(),
            api_enabled=bool(data.get("api_enabled")),
        )
        city = (data.get("pickup_city") or "").strip()
        line1 = (data.get("pickup_line1") or "").strip()
        if city and line1:
            lat, lng = city_center(city)
            address = Address.objects.create(city=city, line1=line1, latitude=lat, longitude=lng)
            PickupPoint.objects.create(client=client, name="მთავარი", address=address, is_default=True)
        return client


class CourierCreateForm(forms.Form):
    first_name = forms.CharField(max_length=150, label="სახელი")
    last_name = forms.CharField(max_length=150, required=False, label="გვარი")
    email = forms.EmailField(label="ელფოსტა")
    phone = forms.CharField(max_length=20, required=False, label="ტელეფონი")
    password = forms.CharField(widget=forms.PasswordInput, label="პაროლი")
    password2 = forms.CharField(widget=forms.PasswordInput, label="პაროლი თავიდან")
    vehicle_type = forms.ChoiceField(choices=CourierProfile.VehicleType.choices, label="ტრანსპორტი")
    vehicle_plate = forms.CharField(max_length=20, required=False, label="ნომერი")

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
        if password:
            try:
                validate_password(password)
            except ValidationError as exc:
                self.add_error("password", exc.messages)
        return cleaned

    def save(self, company):
        data = self.cleaned_data
        user = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            role=User.Role.COURIER,
            first_name=data["first_name"].strip(),
            last_name=(data.get("last_name") or "").strip(),
            phone=(data.get("phone") or "").strip(),
        )
        return CourierProfile.objects.create(
            user=user,
            company=company,
            vehicle_type=data["vehicle_type"],
            vehicle_plate=(data.get("vehicle_plate") or "").strip(),
        )
