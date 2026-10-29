from django.contrib import admin

from .models import CourierProfile, Device


class DeviceInline(admin.TabularInline):
    model = Device
    extra = 0
    readonly_fields = ("fcm_token", "last_seen_at")


@admin.register(CourierProfile)
class CourierProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "vehicle_type", "status", "is_active", "last_location_at")
    list_filter = ("company", "status", "vehicle_type", "is_active")
    search_fields = ("user__email", "user__first_name", "user__last_name", "vehicle_plate")
    autocomplete_fields = ("user", "company")
    readonly_fields = ("last_latitude", "last_longitude", "last_location_at")
    inlines = [DeviceInline]


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("courier", "platform", "model_name", "app_version", "is_active", "last_seen_at")
    list_filter = ("platform", "is_active")
    search_fields = ("courier__user__email", "device_id", "model_name")
    autocomplete_fields = ("courier",)
