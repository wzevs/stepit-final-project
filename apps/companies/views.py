from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.clients.models import Client
from apps.couriers.models import CourierProfile
from apps.shipments.labels import STATUS_KA
from apps.shipments.models import Shipment
from apps.shipments.services import REASSIGNABLE, ShipmentError, assign_courier, unassign_courier

from .forms import ClientCreateForm, CourierCreateForm
from .live import live_couriers
from .models import CompanyMembership

WRITER_ROLES = {CompanyMembership.Role.OWNER, CompanyMembership.Role.DISPATCHER}


class CompanyMixin(LoginRequiredMixin):
    login_url = "/manage/login/"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.memberships = list(
            request.user.company_memberships.filter(is_active=True, company__is_active=True).select_related(
                "company"
            )
        )
        if not self.memberships:
            return render(request, "manage/no_access.html", status=403)
        wanted = request.session.get("manage_company_id")
        match = next((m for m in self.memberships if str(m.company_id) == wanted), None)
        self.membership = match or self.memberships[0]
        self.company = self.membership.company
        self.can_manage = self.membership.role in WRITER_ROLES
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._base_context())
        return context

    def _base_context(self):
        return {
            "company": self.company,
            "memberships": self.memberships,
            "can_manage": self.can_manage,
            "status_ka": STATUS_KA,
        }

    def forbid_viewer(self, request):
        if self.can_manage:
            return None
        return render(request, "manage/no_access.html", status=403)


class ManageLoginView(LoginView):
    template_name = "manage/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return "/manage/shipments/"


class ManageLogoutView(LogoutView):
    next_page = "/manage/login/"


class SwitchCompanyView(CompanyMixin, View):
    def post(self, request):
        chosen = request.POST.get("company_id")
        if any(str(m.company_id) == chosen for m in self.memberships):
            request.session["manage_company_id"] = chosen
        return redirect("manage:shipment-list")


class ShipmentListView(CompanyMixin, ListView):
    template_name = "manage/shipment_list.html"
    context_object_name = "shipments"
    paginate_by = 25

    def get_queryset(self):
        qs = Shipment.objects.filter(company=self.company).select_related(
            "client", "courier__user", "delivery_address"
        )
        status = self.request.GET.get("status")
        if status in Shipment.Status.values:
            qs = qs.filter(status=status)
        client_id = self.request.GET.get("client")
        if client_id:
            qs = qs.filter(client_id=client_id)
        query = (self.request.GET.get("q") or "").strip()
        if query:
            qs = qs.filter(
                Q(tracking_number__icontains=query)
                | Q(recipient_phone__icontains=query)
                | Q(recipient_name__icontains=query)
                | Q(external_id__icontains=query)
                | Q(client__name__icontains=query)
            )
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["clients"] = Client.objects.filter(company=self.company, is_active=True)
        return context


class ShipmentDetailView(CompanyMixin, View):
    def get(self, request, pk):
        shipment = self._shipment(pk)
        return render(request, "manage/shipment_detail.html", self._context(shipment))

    def post(self, request, pk):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        shipment = self._shipment(pk)
        courier_id = (request.POST.get("courier_id") or "").strip()
        note = (request.POST.get("note") or "").strip()
        try:
            if not courier_id:
                unassign_courier(shipment, actor=request.user, note=note)
                messages.success(request, "კურიერი მოხსნილია.")
            else:
                courier = get_object_or_404(
                    CourierProfile, pk=courier_id, company=self.company, is_active=True
                )
                if shipment.status not in REASSIGNABLE:
                    messages.error(request, "ამ სტატუსზე კურიერის შეცვლა არ შეიძლება.")
                else:
                    assign_courier(shipment, courier, actor=request.user, note=note)
                    messages.success(request, "კურიერი დანიშნულია.")
        except ShipmentError:
            messages.error(request, "კურიერის შეცვლა ვერ მოხერხდა.")
        return redirect("manage:shipment-detail", pk=shipment.pk)

    def _shipment(self, pk):
        return get_object_or_404(
            Shipment.objects.select_related("client", "courier__user", "pickup_address", "delivery_address"),
            pk=pk,
            company=self.company,
        )

    def _context(self, shipment):
        couriers = CourierProfile.objects.filter(company=self.company, is_active=True).select_related("user")
        context = self._base_context()
        context.update(
            {
                "shipment": shipment,
                "events": shipment.events.all(),
                "couriers": couriers,
                "can_assign": self.can_manage and shipment.status in REASSIGNABLE,
                "can_unassign": self.can_manage and shipment.status == Shipment.Status.ASSIGNED,
            }
        )
        return context


class ClientListView(CompanyMixin, ListView):
    template_name = "manage/client_list.html"
    context_object_name = "clients"

    def get_queryset(self):
        return Client.objects.filter(company=self.company).order_by("name")


class ClientCreateView(CompanyMixin, View):
    template_name = "manage/client_form.html"

    def get(self, request):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        return render(
            request,
            self.template_name,
            {**self._base_context(), "form": ClientCreateForm(company=self.company)},
        )

    def post(self, request):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        form = ClientCreateForm(request.POST, company=self.company)
        if not form.is_valid():
            return render(request, self.template_name, {**self._base_context(), "form": form})
        client = form.save()
        messages.success(request, f"მაღაზია დაემატა: {client.name}")
        return redirect("manage:client-list")


class LiveMapView(CompanyMixin, TemplateView):
    template_name = "manage/map.html"


class LiveCouriersView(CompanyMixin, View):
    def get(self, request):
        return JsonResponse(live_couriers(self.company))


class CourierListView(CompanyMixin, ListView):
    template_name = "manage/courier_list.html"
    context_object_name = "couriers"

    def get_queryset(self):
        return (
            CourierProfile.objects.filter(company=self.company)
            .select_related("user")
            .order_by("user__first_name", "user__email")
        )


class CourierCreateView(CompanyMixin, View):
    template_name = "manage/courier_form.html"

    def get(self, request):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        return render(request, self.template_name, {**self._base_context(), "form": CourierCreateForm()})

    def post(self, request):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        form = CourierCreateForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {**self._base_context(), "form": form})
        with transaction.atomic():
            profile = form.save(self.company)
        messages.success(request, f"კურიერი დაემატა: {profile.user.get_full_name() or profile.user.email}")
        return redirect("manage:courier-list")
