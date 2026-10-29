from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "shipment",
        "channel",
        "recipient",
        "template",
        "status",
        "attempts",
        "sent_at",
        "created_at",
    )
    list_filter = ("channel", "status", "template")
    search_fields = ("shipment__tracking_number", "recipient")
    autocomplete_fields = ("shipment",)
    readonly_fields = ("provider_message_id", "error", "attempts", "sent_at", "created_at")
