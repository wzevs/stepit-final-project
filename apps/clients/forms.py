from django import forms

from apps.clients.models import PickupPoint
from apps.shipments.creation import pickup_points_for
from apps.shipments.models import Shipment


class ShipmentCreateForm(forms.Form):
    external_id = forms.CharField(max_length=100, required=False, label="შეკვეთის ნომერი")
    pickup_point = forms.ModelChoiceField(
        queryset=PickupPoint.objects.none(), required=False, label="აღების წერტილი"
    )
    pickup_city = forms.CharField(max_length=100, required=False, label="აღება: ქალაქი")
    pickup_line1 = forms.CharField(max_length=255, required=False, label="აღება: მისამართი")
    delivery_city = forms.CharField(max_length=100, label="მიწოდება: ქალაქი")
    delivery_line1 = forms.CharField(max_length=255, label="მიწოდება: მისამართი")
    delivery_line2 = forms.CharField(max_length=255, required=False, label="სადარბაზო, სართული, ბინა")
    delivery_notes = forms.CharField(max_length=255, required=False, label="შენიშვნა კურიერისთვის")
    recipient_name = forms.CharField(max_length=150, label="მიმღები")
    recipient_phone = forms.CharField(max_length=20, label="ტელეფონი")
    recipient_email = forms.EmailField(required=False, label="ელფოსტა")
    description = forms.CharField(max_length=255, required=False, label="აღწერა")
    weight_kg = forms.DecimalField(max_digits=7, decimal_places=3, required=False, label="წონა (კგ)")
    payment_type = forms.ChoiceField(choices=Shipment.PaymentType.choices, label="გადახდა")
    cod_amount = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, label="თანხა მიწოდებისას"
    )
    is_fragile = forms.BooleanField(required=False, label="მყიფე")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="შენიშვნა")
    scheduled_delivery_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}), label="მიწოდების თარიღი"
    )

    def __init__(self, *args, client, **kwargs):
        self.client = client
        super().__init__(*args, **kwargs)
        self.fields["pickup_point"].queryset = pickup_points_for(client)
        self.fields["pickup_point"].empty_label = "მისამართს ხელით მივუთითებ"

    def clean(self):
        cleaned = super().clean()
        has_point = bool(cleaned.get("pickup_point"))
        has_pickup = bool(cleaned.get("pickup_city") and cleaned.get("pickup_line1"))
        if not has_point and not has_pickup:
            raise forms.ValidationError("აირჩიეთ აღების წერტილი ან მიუთითეთ აღების მისამართი.")
        if cleaned.get("payment_type") == Shipment.PaymentType.COD and not cleaned.get("cod_amount"):
            self.add_error("cod_amount", "თანხა აუცილებელია, როცა გადახდა მიწოდებისას ხდება.")
        return cleaned

    def to_payload(self) -> dict:
        data = self.cleaned_data
        pickup = None
        if data.get("pickup_city") and data.get("pickup_line1"):
            pickup = {"city": data["pickup_city"], "line1": data["pickup_line1"]}
        return {
            "external_id": data.get("external_id") or "",
            "pickup_point": data.get("pickup_point"),
            "pickup_address": pickup,
            "delivery_address": {
                "city": data["delivery_city"],
                "line1": data["delivery_line1"],
                "line2": data.get("delivery_line2") or "",
                "notes": data.get("delivery_notes") or "",
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
        }
