from django.contrib import admin

from apps.network.models import City, District, ShopTariff, Tariff, Warehouse, WeightBand


class DistrictInline(admin.TabularInline):
    model = District
    extra = 0


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    inlines = [DistrictInline]


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "city")
    list_filter = ("city",)
    search_fields = ("name", "city__name")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "kind", "city", "district", "is_active")
    list_filter = ("kind", "is_active", "city")
    search_fields = ("name",)
    autocomplete_fields = ("company", "address")


@admin.register(WeightBand)
class WeightBandAdmin(admin.ModelAdmin):
    list_display = ("company", "min_kg", "max_kg", "surcharge")
    list_filter = ("company",)
    autocomplete_fields = ("company",)


@admin.register(ShopTariff)
class ShopTariffAdmin(admin.ModelAdmin):
    list_display = ("client", "company", "standard_price")
    autocomplete_fields = ("company", "client")


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ("company", "kind", "price", "origin_city", "destination_city", "is_active")
    list_filter = ("kind", "is_active")
    autocomplete_fields = ("company",)
