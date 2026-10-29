from django.contrib import admin, messages

from .models import ApiKey, Webhook, WebhookDelivery


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("client", "name", "prefix", "is_active", "last_used_at", "expires_at", "created_at")
    list_filter = ("is_active", "client__company")
    search_fields = ("client__name", "name", "prefix")
    autocomplete_fields = ("client",)
    readonly_fields = ("prefix", "key_hash", "last_used_at", "created_at")

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        # New key: generate it and show the raw value exactly once.
        api_key, raw = ApiKey.issue(client=obj.client, name=obj.name)
        api_key.is_active = obj.is_active
        api_key.expires_at = obj.expires_at
        api_key.save()
        obj.pk = api_key.pk
        messages.warning(request, f"API key created. Copy it now, it will not be shown again: {raw}")


@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ("client", "url", "is_active", "created_at")
    list_filter = ("is_active", "client__company")
    search_fields = ("client__name", "url")
    autocomplete_fields = ("client",)


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ("webhook", "event", "response_status", "attempts", "delivered_at", "created_at")
    list_filter = ("event", "response_status")
    search_fields = ("webhook__url", "webhook__client__name")
    readonly_fields = ("payload", "response_body", "created_at")
