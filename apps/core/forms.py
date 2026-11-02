from django import forms

from apps.shipments.models import Shipment


class GuestSendForm(forms.Form):
    sender_name = forms.CharField(max_length=150, label="თქვენი სახელი")
    sender_phone = forms.CharField(max_length=20, label="თქვენი ტელეფონი")
    sender_email = forms.EmailField(label="თქვენი ელფოსტა")
    pickup_city = forms.CharField(max_length=100, label="საიდან: ქალაქი")
    pickup_line1 = forms.CharField(max_length=255, label="საიდან: მისამართი")
    recipient_name = forms.CharField(max_length=150, label="მიმღები")
    recipient_phone = forms.CharField(max_length=20, label="მიმღების ტელეფონი")
    recipient_email = forms.EmailField(label="მიმღების ელფოსტა")
    delivery_city = forms.CharField(max_length=100, label="სად: ქალაქი")
    delivery_line1 = forms.CharField(max_length=255, label="სად: მისამართი")
    delivery_line2 = forms.CharField(max_length=255, required=False, label="სადარბაზო, სართული, ბინა")
    description = forms.CharField(max_length=255, required=False, label="რას აგზავნით")
    is_fragile = forms.BooleanField(required=False, label="მყიფეა")

    def to_payload(self) -> dict:
        data = self.cleaned_data
        sender = f"{data['sender_name'].strip()}, {data['sender_phone'].strip()}"
        return {
            "pickup_address": {"city": data["pickup_city"], "line1": data["pickup_line1"]},
            "delivery_address": {
                "city": data["delivery_city"],
                "line1": data["delivery_line1"],
                "line2": data.get("delivery_line2") or "",
            },
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
