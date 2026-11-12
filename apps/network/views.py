from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.companies.views import CompanyMixin
from apps.network.forms import (
    CityForm,
    CityTariffForm,
    CutoffForm,
    DistrictForm,
    DistrictTariffForm,
    MoneyForm,
    QuoteTryForm,
    ShopPriceForm,
    WarehouseForm,
    WeightBandForm,
)
from apps.network.models import City, District, ShopTariff, Tariff, Warehouse, WeightBand
from apps.network.quote import quote_shipping


class PlaceListView(CompanyMixin, View):
    template_name = "manage/place_list.html"

    def get(self, request):
        return render(request, self.template_name, self._context())

    def post(self, request):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        intent = request.POST.get("intent")
        if intent == "city":
            form = CityForm(request.POST)
            if form.is_valid():
                city = form.save()
                messages.success(request, f"ქალაქი დაემატა: {city.name}")
                return redirect("manage:place-list")
            return render(request, self.template_name, self._context(city_form=form))
        if intent == "district":
            form = DistrictForm(request.POST)
            if form.is_valid():
                district = form.save()
                messages.success(request, f"უბანი დაემატა: {district}")
                return redirect("manage:place-list")
            return render(request, self.template_name, self._context(district_form=form))
        messages.error(request, "უცნობი მოქმედება.")
        return redirect("manage:place-list")

    def _context(self, city_form=None, district_form=None):
        return {
            **self._base_context(),
            "cities": City.objects.prefetch_related("districts").order_by("name"),
            "city_form": city_form or CityForm(),
            "district_form": district_form or DistrictForm(),
        }


class WarehouseListView(CompanyMixin, View):
    template_name = "manage/warehouse_list.html"

    def get(self, request):
        warehouses = (
            Warehouse.objects.filter(company=self.company)
            .select_related("city", "district", "address")
            .order_by("city__name", "kind", "name")
        )
        return render(request, self.template_name, {**self._base_context(), "warehouses": warehouses})


class WarehouseFormView(CompanyMixin, View):
    template_name = "manage/warehouse_form.html"

    def get(self, request, pk=None):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        warehouse = self._warehouse(pk)
        return render(request, self.template_name, self._context(self._form(warehouse), warehouse))

    def post(self, request, pk=None):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        warehouse = self._warehouse(pk)
        form = self._form(warehouse, data=request.POST)
        if not form.is_valid():
            return render(request, self.template_name, self._context(form, warehouse))
        try:
            saved = form.save()
        except IntegrityError:
            form.add_error(None, "საწყობის ტიპი და უბანი ერთმანეთს არ ემთხვევა.")
            return render(request, self.template_name, self._context(form, warehouse))
        messages.success(request, f"საწყობი შენახულია: {saved.name}")
        return redirect("manage:warehouse-list")

    def _warehouse(self, pk):
        if pk is None:
            return None
        return get_object_or_404(
            Warehouse.objects.select_related("address", "city", "district"),
            pk=pk,
            company=self.company,
        )

    def _form(self, warehouse, data=None):
        initial = None
        if data is None and warehouse is not None:
            initial = {
                "name": warehouse.name,
                "kind": warehouse.kind,
                "city": warehouse.city_id,
                "district": warehouse.district_id,
                "line1": warehouse.address.line1,
                "latitude": warehouse.address.latitude,
                "longitude": warehouse.address.longitude,
                "is_active": warehouse.is_active,
            }
        return WarehouseForm(data, company=self.company, instance=warehouse, initial=initial)

    def _context(self, form, warehouse):
        districts = [
            {"id": row.pk, "city_id": row.city_id, "label": str(row)}
            for row in District.objects.order_by("city__name", "name")
        ]
        return {**self._base_context(), "form": form, "warehouse": warehouse, "districts": districts}


class TariffBoardView(CompanyMixin, View):
    template_name = "manage/tariff_board.html"

    def get(self, request):
        return render(request, self.template_name, self._context())

    def post(self, request):
        denied = self.forbid_viewer(request)
        if denied:
            return denied
        intent = request.POST.get("intent")
        if intent == "delete":
            row = get_object_or_404(Tariff, pk=request.POST.get("tariff_id"), company=self.company)
            row.delete()
            messages.success(request, "ტარიფი წაიშალა.")
            return redirect("manage:tariff-board")
        if intent == "delete_weight":
            band = get_object_or_404(WeightBand, pk=request.POST.get("band_id"), company=self.company)
            band.delete()
            messages.success(request, "წონის საფეხური წაიშალა.")
            return redirect("manage:tariff-board")
        if intent == "try":
            form = QuoteTryForm(request.POST)
            quote = None
            if form.is_valid():
                quote = quote_shipping(
                    company=self.company,
                    origin=form.cleaned_data["origin_district"],
                    destination=form.cleaned_data["destination_district"],
                    home_delivery=bool(form.cleaned_data.get("home_delivery")),
                    weight_kg=form.cleaned_data.get("weight_kg"),
                )
            return render(request, self.template_name, self._context(try_form=form, quote=quote))
        saved = self._save(intent, request.POST)
        if isinstance(saved, str):
            messages.error(request, saved)
            return redirect("manage:tariff-board")
        if saved is None:
            messages.error(request, "შეავსეთ ფასი და მიმართულება.")
            return render(request, self.template_name, self._context(open_intent=intent, posted=request.POST))
        messages.success(request, "ტარიფი შენახულია.")
        return redirect("manage:tariff-board")

    def _save(self, intent, data):
        if intent == "standard":
            form = MoneyForm(data)
            if not form.is_valid():
                return None
            _upsert_flat(self.company, Tariff.Kind.STANDARD, form.cleaned_data["price"])
            return True
        if intent == "home":
            form = MoneyForm(data)
            if not form.is_valid():
                return None
            _upsert_flat(self.company, Tariff.Kind.HOME, form.cleaned_data["price"])
            return True
        if intent == "city":
            form = CityTariffForm(data)
            if not form.is_valid():
                return None
            _upsert_pair(
                self.company,
                Tariff.Kind.CITY,
                form.cleaned_data["price"],
                origin_city=form.cleaned_data["origin_city"],
                destination_city=form.cleaned_data["destination_city"],
            )
            return True
        if intent == "district":
            form = DistrictTariffForm(data)
            if not form.is_valid():
                return None
            _upsert_pair(
                self.company,
                Tariff.Kind.DISTRICT,
                form.cleaned_data["price"],
                origin_district=form.cleaned_data["origin_district"],
                destination_district=form.cleaned_data["destination_district"],
            )
            return True
        if intent == "weight":
            form = WeightBandForm(data, company=self.company)
            if not form.is_valid():
                return None
            form.save()
            return True
        if intent == "cutoff":
            form = CutoffForm(data)
            if not form.is_valid():
                return None
            self.company.same_day_cutoff = form.cleaned_data["same_day_cutoff"]
            self.company.save(update_fields=["same_day_cutoff", "updated_at"])
            return True
        if intent == "shop":
            form = ShopPriceForm(data, company=self.company)
            if not form.is_valid():
                return None
            client = form.cleaned_data["client"]
            price = form.cleaned_data.get("standard_price")
            if price is None:
                ShopTariff.objects.filter(client=client).delete()
                return True
            ShopTariff.objects.update_or_create(
                client=client,
                defaults={"company": client.company, "standard_price": price},
            )
            return True
        return "უცნობი მოქმედება."

    def _context(self, try_form=None, quote=None, open_intent="", posted=None):
        tariffs = Tariff.objects.filter(company=self.company).select_related(
            "origin_city", "destination_city", "origin_district__city", "destination_district__city"
        )
        return {
            **self._base_context(),
            "standard": tariffs.filter(kind=Tariff.Kind.STANDARD).first(),
            "home": tariffs.filter(kind=Tariff.Kind.HOME).first(),
            "city_rows": tariffs.filter(kind=Tariff.Kind.CITY),
            "district_rows": tariffs.filter(kind=Tariff.Kind.DISTRICT),
            "standard_form": MoneyForm(posted) if open_intent == "standard" else MoneyForm(),
            "home_form": MoneyForm(posted) if open_intent == "home" else MoneyForm(),
            "city_form": CityTariffForm(posted) if open_intent == "city" else CityTariffForm(),
            "district_form": (
                DistrictTariffForm(posted) if open_intent == "district" else DistrictTariffForm()
            ),
            "try_form": try_form or QuoteTryForm(),
            "weight_form": (
                WeightBandForm(posted, company=self.company)
                if open_intent == "weight"
                else WeightBandForm(company=self.company)
            ),
            "weight_rows": WeightBand.objects.filter(company=self.company).order_by("min_kg"),
            "shop_rows": ShopTariff.objects.filter(company=self.company).select_related("client"),
            "shop_form": (
                ShopPriceForm(posted, company=self.company)
                if open_intent == "shop"
                else ShopPriceForm(company=self.company)
            ),
            "cutoff_form": CutoffForm(
                posted if open_intent == "cutoff" else None,
                initial={"same_day_cutoff": self.company.same_day_cutoff},
            ),
            "quote": quote,
            "open_intent": open_intent,
        }


def _upsert_flat(company, kind, price):
    with transaction.atomic():
        row = Tariff.objects.filter(company=company, kind=kind).first()
        if row is None:
            return Tariff.objects.create(company=company, kind=kind, price=price)
        row.price = price
        row.is_active = True
        row.save(update_fields=["price", "is_active", "updated_at"])
        return row


def _upsert_pair(company, kind, price, **keys):
    with transaction.atomic():
        row = Tariff.objects.filter(company=company, kind=kind, **keys).first()
        if row is None:
            return Tariff.objects.create(company=company, kind=kind, price=price, **keys)
        row.price = price
        row.is_active = True
        row.save(update_fields=["price", "is_active", "updated_at"])
        return row
