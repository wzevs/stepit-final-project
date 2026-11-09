from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.clients.models import PickupPoint
from apps.integrations.models import ApiKey
from apps.network.models import District
from apps.network.quote import quote_shipping
from apps.shipments.creation import ShipmentCreateError, create_shipment
from apps.shipments.labels import PAYMENT_KA, SERVICE_KA, STATUS_KA
from apps.shipments.models import Shipment
from apps.shipments.services import InvalidTransition, ShipmentError, allowed_next, transition
from apps.tracking.services import issue_staff_tracking_url

from .forms import BranchForm, ShipmentCreateForm


class ShopMixin(LoginRequiredMixin):
    login_url = "/dashboard/login/"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.memberships = list(
            request.user.client_memberships.filter(is_active=True, client__is_active=True).select_related(
                "client", "client__company"
            )
        )
        if not self.memberships:
            return render(request, "dashboard/no_access.html", status=403)
        wanted = request.session.get("client_id")
        match = next((m for m in self.memberships if str(m.client_id) == wanted), None)
        self.membership = match or self.memberships[0]
        self.shop = self.membership.client
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["shop"] = self.shop
        context["memberships"] = self.memberships
        context["status_ka"] = STATUS_KA
        context["payment_ka"] = PAYMENT_KA
        return context


class DashboardLoginView(LoginView):
    template_name = "dashboard/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return "/dashboard/shipments/"


class DashboardLogoutView(LogoutView):
    next_page = "/dashboard/login/"


class SwitchShopView(ShopMixin, View):
    def post(self, request):
        chosen = request.POST.get("client_id")
        if any(str(m.client_id) == chosen for m in self.memberships):
            request.session["client_id"] = chosen
        return redirect("dashboard:shipment-list")


class ShipmentListView(ShopMixin, ListView):
    template_name = "dashboard/shipment_list.html"
    context_object_name = "shipments"
    paginate_by = 25

    def get_queryset(self):
        qs = Shipment.objects.filter(client=self.shop).select_related("delivery_address")
        status = self.request.GET.get("status")
        if status in Shipment.Status.values:
            qs = qs.filter(status=status)
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(
                Q(tracking_number__icontains=query)
                | Q(recipient_phone__icontains=query)
                | Q(external_id__icontains=query)
                | Q(recipient_name__icontains=query)
            )
        return qs.order_by("-created_at")


class ShipmentCreateView(ShopMixin, View):
    template_name = "dashboard/shipment_form.html"

    def get(self, request):
        form = ShipmentCreateForm(client=self.shop)
        return render(request, self.template_name, self._context(form))

    def post(self, request):
        form = ShipmentCreateForm(request.POST, client=self.shop)
        if not form.is_valid():
            return render(request, self.template_name, self._context(form))
        try:
            shipment, created = create_shipment(
                client=self.shop,
                source=Shipment.Source.MANUAL,
                created_by=request.user,
                payload=form.to_payload(),
            )
        except ShipmentCreateError as exc:
            _apply_create_error(form, exc.detail)
            return render(request, self.template_name, self._context(form))
        if created:
            messages.success(request, f"ამანათი შეიქმნა: {shipment.tracking_number}")
        else:
            messages.info(request, f"ეს შეკვეთა უკვე არსებობს: {shipment.tracking_number}")
        return redirect("dashboard:shipment-detail", pk=shipment.pk)

    def _context(self, form):
        branches = [
            {"id": point.pk, "district_id": point.district_id}
            for point in form.fields["pickup_point"].queryset
        ]
        return {
            "form": form,
            "shop": self.shop,
            "memberships": self.memberships,
            "status_ka": STATUS_KA,
            "branches": branches,
        }


class ShipmentDetailView(ShopMixin, View):
    def get(self, request, pk):
        shipment = self._shipment(pk)
        tracking_url = request.session.pop("tracking_url", "")
        events = shipment.events.filter(is_public=True)
        return render(
            request,
            "dashboard/shipment_detail.html",
            {
                "shipment": shipment,
                "events": events,
                "shop": self.shop,
                "memberships": self.memberships,
                "status_ka": STATUS_KA,
                "payment_ka": PAYMENT_KA,
                "service_ka": SERVICE_KA,
                "can_cancel": Shipment.Status.CANCELLED in allowed_next(shipment.status),
                "tracking_url": tracking_url,
            },
        )

    def post(self, request, pk):
        shipment = self._shipment(pk)
        intent = request.POST.get("intent")
        note = (request.POST.get("note") or "").strip()
        try:
            if intent == "cancel":
                transition(shipment, Shipment.Status.CANCELLED, actor=request.user, note=note)
                messages.success(request, "ამანათი გაუქმდა.")
            elif intent == "tracking_link":
                request.session["tracking_url"] = issue_staff_tracking_url(shipment)
                messages.success(request, "მიმღების ლინკი მზადაა. დააკოპირეთ ქვემოთ.")
            else:
                messages.error(request, "უცნობი მოქმედება.")
        except (InvalidTransition, ShipmentError):
            messages.error(request, "ეს მოქმედება ამ სტატუსზე არ შეიძლება.")
        return redirect("dashboard:shipment-detail", pk=shipment.pk)

    def _shipment(self, pk):
        return get_object_or_404(
            Shipment.objects.select_related("pickup_address", "delivery_address", "courier__user"),
            pk=pk,
            client=self.shop,
        )


class QuoteView(ShopMixin, View):
    def get(self, request):
        origin = _district(request.GET.get("origin"))
        point_id = request.GET.get("pickup_point")
        if point_id:
            point = (
                PickupPoint.objects.filter(client=self.shop, pk=point_id)
                .select_related("district")
                .first()
            )
            if point is not None and point.district_id:
                origin = point.district
        weight = _weight(request.GET.get("weight"))
        quoted = quote_shipping(
            company=self.shop.company,
            origin=origin,
            destination=_district(request.GET.get("destination")),
            home_delivery=request.GET.get("home") in {"1", "on", "true"},
            weight_kg=weight,
            client=self.shop,
        )
        if quoted is None:
            return JsonResponse({"ok": False, "detail": "სტანდარტული ტარიფი ჯერ არ არის."})
        if quoted.weight_uncovered:
            return JsonResponse({"ok": False, "detail": "ამ წონის საფეხური არ არის."})
        return JsonResponse(
            {
                "ok": True,
                "amount": f"{quoted.amount:.2f}",
                "route_fee": f"{quoted.route_fee:.2f}",
                "home_fee": f"{quoted.home_fee:.2f}",
                "weight_fee": f"{quoted.weight_fee:.2f}",
                "basis": quoted.basis_ka,
            }
        )


def _apply_create_error(form, detail):
    if isinstance(detail, dict):
        for key, message in detail.items():
            if key in form.fields:
                form.add_error(key, message)
            else:
                form.add_error(None, message)
        return
    form.add_error(None, detail if isinstance(detail, str) else "ამანათი ვერ შეიქმნა.")


def _district(raw):
    if not raw:
        return None
    return District.objects.filter(pk=raw).first()


def _weight(raw):
    if raw in (None, ""):
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        return None
    if value < 0:
        return None
    return value


class BranchListView(ShopMixin, ListView):
    template_name = "dashboard/branch_list.html"
    context_object_name = "branches"

    def get_queryset(self):
        return (
            PickupPoint.objects.filter(client=self.shop)
            .select_related("address", "district", "district__city")
            .order_by("-is_default", "name")
        )


class BranchFormView(ShopMixin, View):
    template_name = "dashboard/branch_form.html"

    def get(self, request, pk=None):
        branch = self._branch(pk)
        return render(request, self.template_name, self._context(self._form(branch), branch))

    def post(self, request, pk=None):
        branch = self._branch(pk)
        form = self._form(branch, data=request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._context(form, branch))
        saved = form.save()
        messages.success(request, f"ფილიალი შენახულია: {saved.name}")
        return redirect("dashboard:branch-list")

    def _branch(self, pk):
        if pk is None:
            return None
        return get_object_or_404(
            PickupPoint.objects.select_related("address", "district"), pk=pk, client=self.shop
        )

    def _form(self, branch, data=None):
        initial = None
        if data is None and branch is not None:
            initial = {
                "name": branch.name,
                "district": branch.district_id,
                "contact_phone": branch.contact_phone,
                "line1": branch.address.line1,
                "latitude": branch.address.latitude,
                "longitude": branch.address.longitude,
                "opens_at": branch.opens_at,
                "closes_at": branch.closes_at,
                "is_default": branch.is_default,
            }
        return BranchForm(data, shop=self.shop, instance=branch, initial=initial)

    def _context(self, form, branch):
        return {
            "form": form,
            "branch": branch,
            "shop": self.shop,
            "memberships": self.memberships,
        }


class ApiAccessView(ShopMixin, View):
    template_name = "dashboard/api.html"

    def get(self, request):
        raw = request.session.pop("new_api_key", "")
        return render(request, self.template_name, self._context(raw_key=raw))

    def post(self, request):
        intent = request.POST.get("intent")
        if intent == "issue":
            name = (request.POST.get("name") or "").strip() or "API"
            if not self.shop.api_enabled:
                self.shop.api_enabled = True
                self.shop.save(update_fields=["api_enabled"])
            _key, raw = ApiKey.issue(self.shop, name)
            request.session["new_api_key"] = raw
            messages.success(request, "გასაღები შექმნილია. დააკოპირეთ ახლა — ხელახლა ვერ გამოჩნდება.")
        elif intent == "revoke":
            key = get_object_or_404(ApiKey, pk=request.POST.get("key_id"), client=self.shop)
            key.is_active = False
            key.save(update_fields=["is_active"])
            messages.success(request, "გასაღები გაუქმდა.")
        else:
            messages.error(request, "უცნობი მოქმედება.")
        return redirect("dashboard:api-access")

    def _context(self, raw_key=""):
        return {
            "shop": self.shop,
            "memberships": self.memberships,
            "keys": self.shop.api_keys.all(),
            "raw_key": raw_key,
        }


class ShipmentLabelView(ShopMixin, View):
    def get(self, request, pk):
        shipment = get_object_or_404(
            Shipment.objects.select_related("pickup_address", "delivery_address", "client", "company"),
            pk=pk,
            client=self.shop,
        )
        return render(
            request,
            "shipments/label.html",
            {
                "shipment": shipment,
                "shop": self.shop,
                "memberships": self.memberships,
                "status_ka": STATUS_KA,
            },
        )
