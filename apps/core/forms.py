from django import forms

from apps.companies.choice import ANY, company_choices, resolve_company
from apps.core.geo import require_coords
from apps.shipments.models import Shipment


class GuestSendForm(forms.Form):
    company = forms.ChoiceField(
        required=False,
        label="საკურიერო კომპანია",
        help_text="სულ ერთია ნიშნავს: ავირჩევთ კომპანიას, რომელსაც ახლა თავისუფალი კურიერი ჰყავს.",
    )
    sender_name = forms.CharField(max_length=150, label="თქვენი სახელი")
    sender_phone = forms.CharField(max_length=20, label="თქვენი ტელეფონი")
    sender_email = forms.EmailField(label="თქვენი ელფოსტა")
    pickup_city = forms.CharField(max_length=100, label="საიდან: ქალაქი")
    pickup_line1 = forms.CharField(max_length=255, label="საიდან: მისამართი")
    pickup_lat = forms.DecimalField(
        max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput
    )
    pickup_lng = forms.DecimalField(
        max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput
    )
    recipient_name = forms.CharField(max_length=150, label="მიმღები")
    recipient_phone = forms.CharField(max_length=20, label="მიმღების ტელეფონი")
    recipient_email = forms.EmailField(label="მიმღების ელფოსტა")
    delivery_city = forms.CharField(max_length=100, label="სად: ქალაქი")
    delivery_line1 = forms.CharField(max_length=255, label="სად: მისამართი")
    delivery_lat = forms.DecimalField(
        max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput
    )
    delivery_lng = forms.DecimalField(
        max_digits=9, decimal_places=6, required=False, widget=forms.HiddenInput
    )
    delivery_line2 = forms.CharField(max_length=255, required=False, label="სადარბაზო, სართული, ბინა")
    description = forms.CharField(max_length=255, required=False, label="რას აგზავნით")
    is_fragile = forms.BooleanField(required=False, label="მყიფეა")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].choices = company_choices()
        self.fields["company"].initial = ANY

    def clean_company(self):
        return resolve_company(self.cleaned_data.get("company") or ANY)

    def clean(self):
        cleaned = super().clean()
        try:
            require_coords(cleaned.get("pickup_lat"), cleaned.get("pickup_lng"))
            require_coords(cleaned.get("delivery_lat"), cleaned.get("delivery_lng"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned

    def to_payload(self) -> dict:
        data = self.cleaned_data
        sender = f"{data['sender_name'].strip()}, {data['sender_phone'].strip()}"
        pickup = {
            "city": data["pickup_city"],
            "line1": data["pickup_line1"],
            **require_coords(data.get("pickup_lat"), data.get("pickup_lng")),
        }
        delivery = {
            "city": data["delivery_city"],
            "line1": data["delivery_line1"],
            "line2": data.get("delivery_line2") or "",
            **require_coords(data.get("delivery_lat"), data.get("delivery_lng")),
        }
        return {
            "pickup_address": pickup,
            "delivery_address": delivery,
            "recipient_name": data["recipient_name"],
            "recipient_phone": data["recipient_phone"],
            "recipient_email": data["recipient_email"].strip(),
            "description": data.get("description") or "",
            "payment_type": Shipment.PaymentType.PREPAID,
            "is_fragile": bool(data.get("is_fragile")),
            "notes": f"გამგზავნი: {sender}",
            "metadata": {
                "sender_name": data["sender_name"].strip(),
                "sender_phone": data["sender_phone"].strip(),
                "sender_email": data["sender_email"].strip(),
            },
        }
