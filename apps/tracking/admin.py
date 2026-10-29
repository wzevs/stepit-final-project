from django.contrib import admin

from .models import CourierLocation, TrackingToken


@admin.register(CourierLocation)
class CourierLocationAdmin(admin.ModelAdmin):
    list_display = (
        "courier",
        "latitude",
        "longitude",
        "accuracy_m",
        "speed_mps",
        "recorded_at",
        "received_at",
    )
    list_filter = ("courier__company",)
    search_fields = ("courier__user__email",)
    autocomplete_fields = ("courier",)
    date_hierarchy = "recorded_at"
    readonly_fields = ("received_at",)


@admin.register(TrackingToken)
class TrackingTokenAdmin(admin.ModelAdmin):
    list_display = ("shipment", "sent_via", "expires_at", "revoked_at", "access_count", "last_accessed_at")
    list_filter = ("sent_via",)
    search_fields = ("shipment__tracking_number",)
    autocomplete_fields = ("shipment",)
    readonly_fields = ("token_hash", "access_count", "last_accessed_at", "created_at")
