from django.contrib import admin

from .models import Shipment, ShipmentEvent


class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    can_delete = False
    readonly_fields = (
        "kind",
        "from_status",
        "to_status",
        "actor",
        "note",
        "latitude",
        "longitude",
        "created_at",
    )
    fields = readonly_fields + ("is_public",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        "tracking_number",
        "status",
        "company",
        "client",
        "courier",
        "recipient_name",
        "recipient_phone",
        "scheduled_delivery_date",
        "created_at",
    )
    list_filter = ("status", "source", "payment_type", "company", "client")
    search_fields = ("tracking_number", "external_id", "recipient_name", "recipient_phone")
    autocomplete_fields = (
        "company",
        "client",
        "courier",
        "pickup_point",
        "pickup_address",
        "delivery_address",
        "created_by",
    )
    readonly_fields = ("tracking_number", "picked_up_at", "delivered_at", "created_at", "updated_at")
    date_hierarchy = "created_at"
    inlines = [ShipmentEventInline]
    fieldsets = (
        (None, {"fields": ("tracking_number", "status", "source", "external_id")}),
        ("Ownership", {"fields": ("company", "client", "courier", "created_by")}),
        ("Route", {"fields": ("pickup_point", "pickup_address", "delivery_address")}),
        ("Recipient", {"fields": ("recipient_name", "recipient_phone", "recipient_email")}),
        (
            "Parcel",
            {
                "fields": (
                    "description",
                    "weight_kg",
                    "dimensions_cm",
                    "declared_value",
                    "payment_type",
                    "cod_amount",
                    "is_fragile",
                    "notes",
                )
            },
        ),
        (
            "Timing",
            {"fields": ("scheduled_pickup_at", "scheduled_delivery_date", "picked_up_at", "delivered_at")},
        ),
        (
            "Proof of delivery",
            {"fields": ("proof_photo", "proof_signature", "received_by", "failure_reason")},
        ),
        ("Meta", {"classes": ("collapse",), "fields": ("metadata", "created_at", "updated_at")}),
    )


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(admin.ModelAdmin):
    list_display = ("shipment", "kind", "from_status", "to_status", "actor", "is_public", "created_at")
    list_filter = ("kind", "is_public")
    search_fields = ("shipment__tracking_number", "note")
    autocomplete_fields = ("shipment", "actor")
    readonly_fields = ("created_at",)
