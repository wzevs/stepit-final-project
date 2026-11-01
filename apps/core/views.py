from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import redirect, render
from django.views import View

from apps.couriers.models import CourierProfile
from apps.shipments.labels import STATUS_KA
from apps.shipments.models import Shipment

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


def _role_matches(user, role: str) -> bool:
    if role == "shop":
        return user.client_memberships.filter(is_active=True, client__is_active=True).exists()
    if role == "courier":
        return CourierProfile.objects.filter(user=user, is_active=True, company__is_active=True).exists()
    if role == "owner":
        return user.company_memberships.filter(is_active=True, company__is_active=True).exists()
    return False
