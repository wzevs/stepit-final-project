from django.contrib import admin

from .models import Address


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("id", "city", "line1", "latitude", "longitude", "created_at")
    list_filter = ("country", "city")
    search_fields = ("city", "line1", "formatted", "google_place_id")
