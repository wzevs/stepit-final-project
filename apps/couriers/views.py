from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import ListView, TemplateView

from apps.couriers.models import CourierProfile
from apps.shipments.labels import STATUS_KA
from apps.shipments.models import Shipment


class CourierMixin(LoginRequiredMixin):
    login_url = "/login/"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        profile = (
            CourierProfile.objects.filter(user=request.user, is_active=True, company__is_active=True)
            .select_related("user", "company")
            .first()
        )
        if profile is None:
            return render(request, "courier/no_access.html", status=403)
        self.courier = profile
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["courier"] = self.courier
        context["status_ka"] = STATUS_KA
        return context


class CourierMapView(TemplateView):
    """
    Public shell. Each browser tab authenticates with JWT in sessionStorage,
    so three couriers can stay logged in at once without sharing a cookie.
    """

    template_name = "courier/map.html"

    @method_decorator(ensure_csrf_cookie)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_ka"] = STATUS_KA
        return context


class CourierShipmentListView(CourierMixin, ListView):
    template_name = "courier/shipment_list.html"
    context_object_name = "shipments"
    paginate_by = 25

    def get_queryset(self):
        return (
            Shipment.objects.filter(courier=self.courier)
            .select_related("client", "delivery_address")
            .order_by("-created_at")
        )


class CourierLogoutView(LogoutView):
    next_page = "/"
