from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.shipments.creation import ShipmentCreateError, create_shipment
from apps.shipments.models import Shipment

from .forms import ShipmentCreateForm

STATUS_KA = {
    Shipment.Status.DRAFT: "დრაფტი",
    Shipment.Status.PENDING: "ელოდება აღებას",
    Shipment.Status.ASSIGNED: "კურიერი დანიშნულია",
    Shipment.Status.PICKED_UP: "აღებულია",
    Shipment.Status.IN_TRANSIT: "გზაშია",
    Shipment.Status.OUT_FOR_DELIVERY: "მიაქვთ მიმღებთან",
    Shipment.Status.DELIVERED: "ჩაბარებულია",
    Shipment.Status.FAILED: "ვერ ჩაბარდა",
    Shipment.Status.RETURNED: "დაბრუნებულია",
    Shipment.Status.CANCELLED: "გაუქმებულია",
}


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
            form.add_error(None, exc.detail if isinstance(exc.detail, str) else "ამანათი ვერ შეიქმნა.")
            return render(request, self.template_name, self._context(form))
        if created:
            messages.success(request, f"ამანათი შეიქმნა: {shipment.tracking_number}")
        else:
            messages.info(request, f"ეს შეკვეთა უკვე არსებობს: {shipment.tracking_number}")
        return redirect("dashboard:shipment-detail", pk=shipment.pk)

    def _context(self, form):
        return {"form": form, "shop": self.shop, "memberships": self.memberships, "status_ka": STATUS_KA}


class ShipmentDetailView(ShopMixin, View):
    def get(self, request, pk):
        shipment = get_object_or_404(
            Shipment.objects.select_related("pickup_address", "delivery_address", "courier__user"),
            pk=pk,
            client=self.shop,
        )
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
            },
        )
