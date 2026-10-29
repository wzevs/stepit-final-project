import hashlib
import secrets

from django.db import models
from django.utils import timezone

from apps.clients.models import Client
from apps.core.models import TimeStampedModel


class ApiKey(TimeStampedModel):
    """
    API key for a client's own software. Only the hash is stored; `prefix`
    is shown in the UI so the client can recognise which key is which.
    Header: X-API-Key: lgx_<prefix>_<secret>
    """

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100, help_text='e.g. "ERP production"')
    prefix = models.CharField(max_length=8, unique=True, editable=False)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(cls, client: Client, name: str) -> tuple["ApiKey", str]:
        """Returns (api_key_obj, raw_key). Raw key is shown to the client once."""
        prefix = secrets.token_hex(4)
        raw = f"lgx_{prefix}_{secrets.token_urlsafe(32)}"
        obj = cls.objects.create(client=client, name=name, prefix=prefix, key_hash=cls.hash_key(raw))
        return obj, raw

    @classmethod
    def resolve(cls, raw: str) -> "ApiKey | None":
        try:
            key = cls.objects.select_related("client", "client__company").get(key_hash=cls.hash_key(raw))
        except cls.DoesNotExist:
            return None
        return key if key.is_valid else None

    @property
    def is_valid(self) -> bool:
        if not self.is_active or not self.client.is_active:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"{self.client.name}: {self.name} ({self.prefix})"


class Webhook(TimeStampedModel):
    """Outbound notification to a client's system, signed with HMAC-SHA256."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="webhooks")
    url = models.URLField()
    secret = models.CharField(max_length=64, default=secrets.token_hex)
    events = models.JSONField(
        default=list, blank=True, help_text='e.g. ["shipment.status_changed", "shipment.delivered"]'
    )
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.client.name} -> {self.url}"


class WebhookDelivery(models.Model):
    id = models.BigAutoField(primary_key=True)
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(max_length=50)
    payload = models.JSONField()
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "webhook deliveries"
        indexes = [models.Index(fields=["delivered_at", "next_retry_at"])]

    def __str__(self) -> str:
        return f"{self.event} -> {self.webhook_id} ({self.response_status})"
