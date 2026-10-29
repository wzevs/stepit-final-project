from django.contrib import admin

from .models import Client, ClientMembership, PickupPoint


class PickupPointInline(admin.TabularInline):
    model = PickupPoint
    extra = 0
    autocomplete_fields = ("address",)


class ClientMembershipInline(admin.TabularInline):
    model = ClientMembership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "company", "contact_phone", "api_enabled", "is_active")
    list_filter = ("company", "api_enabled", "is_active")
    search_fields = ("name", "code", "contact_name", "contact_phone")
    autocomplete_fields = ("company", "billing_address")
    inlines = [PickupPointInline, ClientMembershipInline]


@admin.register(PickupPoint)
class PickupPointAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "address", "is_default", "is_active")
    list_filter = ("is_default", "is_active", "client__company")
    search_fields = ("name", "client__name")
    autocomplete_fields = ("client", "address")


@admin.register(ClientMembership)
class ClientMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "client", "role", "is_active")
    list_filter = ("role", "is_active")
    autocomplete_fields = ("user", "client")
