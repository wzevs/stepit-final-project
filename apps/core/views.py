from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render
from django.views import View

from apps.couriers.models import CourierProfile
from apps.shipments.creation import ShipmentCreateError, create_shipment
from apps.shipments.labels import STATUS_KA
from apps.shipments.models import Shipment

from .forms import GuestSendForm
from .guest import activate_walk_in, walk_in_client

ROLES = {
    "shop": {
        "target": "/dashboard/shipments/",
        "denied": "ეს ანგარიში მაღაზიის არ არის.",
    },
    "courier": {
        "target": "/courier/map/",
        "denied": "ეს ანგარიში კურიერის არ არის.",
    },
    "owner": {
        "target": "/manage/shipments/",
        "denied": "ეს ანგარიში კომპანიის მფლობელის არ არის.",
    },
}


class HomeView(View):
    template_name = "public/home.html"

    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        shipment = None
        events = []
        if query:
            shipment = (
                Shipment.objects.filter(tracking_number__iexact=query)
                .select_related("delivery_address")
                .first()
            )
            if shipment:
                events = shipment.events.filter(is_public=True)
        return render(
            request,
            self.template_name,
            {
                "query": query,
                "shipment": shipment,
                "events": events,
                "searched": bool(query),
                "status_ka": STATUS_KA,
            },
        )


class GateLoginView(View):
    """Role picker plus login. Shop and owner use a session; couriers use the map JWT."""

    template_name = "public/login.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        role = request.POST.get("role")
        email = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        spec = ROLES.get(role)
        user = authenticate(request, username=email, password=password)
        if spec is None:
            messages.error(request, "აირჩიეთ ვინ ხართ.")
            return redirect("/login/")
        if user is None or not user.is_active:
            messages.error(request, "ელფოსტა ან პაროლი არასწორია.")
            return redirect("/login/")
        if not _role_matches(user, role):
            messages.error(request, spec["denied"])
            return redirect(f"/login/?role={role}")
        if role == "courier":
            return redirect(spec["target"])
        login(request, user)
        return redirect(spec["target"])


class GuestSendView(View):
    template_name = "public/send.html"

    def get(self, request):
        tracking = request.session.pop("guest_tracking", "")
        sender_url = request.session.pop("guest_sender_url", "")
        recipient_url = request.session.pop("guest_recipient_url", "")
        assigned = request.session.pop("guest_assigned", False)
        pin = request.session.pop("guest_pin", "")
        return render(
            request,
            self.template_name,
            {
                "form": GuestSendForm(),
                "tracking_number": tracking,
                "sender_url": sender_url,
                "recipient_url": recipient_url,
                "assigned": assigned,
                "recipient_pin": pin,
            },
        )

    def post(self, request):
        form = GuestSendForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "tracking_number": ""})
        client = walk_in_client()
        if client is None:
            form.add_error(None, "მიწოდება ჯერ არ არის ხელმისაწვდომი. სცადეთ მოგვიანებით.")
            return render(request, self.template_name, {"form": form, "tracking_number": ""})
        try:
            shipment, _ = create_shipment(
                client=client,
                source=Shipment.Source.MANUAL,
                payload=form.to_payload(),
            )
        except ShipmentCreateError:
            form.add_error(None, "ამანათი ვერ გაიგზავნა. შეამოწმეთ მისამართები.")
            return render(request, self.template_name, {"form": form, "tracking_number": ""})
        access = activate_walk_in(shipment)
        request.session["guest_tracking"] = shipment.tracking_number
        request.session["guest_sender_url"] = access["sender_url"]
        request.session["guest_recipient_url"] = access["recipient_url"]
        request.session["guest_assigned"] = access["assigned"]
        request.session["guest_pin"] = shipment.recipient_pin
        messages.success(request, f"ამანათი მიღებულია. ტრეკინგი: {shipment.tracking_number}")
        if access.get("email_sent"):
            messages.success(request, "რუკის ლინკი გამგზავნსაც და მიმღებსაც ელფოსტაზე გაეგზავნა.")
        else:
            messages.warning(
                request,
                "ამანათი შეიქმნა, მაგრამ ელფოსტა ვერ გაიგზავნა. შეამოწმეთ SMTP პარამეტრები .env ფაილში.",
            )
        return redirect("guest-send")


def _role_matches(user, role: str) -> bool:
    if role == "shop":
        return user.client_memberships.filter(is_active=True, client__is_active=True).exists()
    if role == "courier":
        return CourierProfile.objects.filter(user=user, is_active=True, company__is_active=True).exists()
    if role == "owner":
        return user.company_memberships.filter(is_active=True, company__is_active=True).exists()
    return False
