from django.db import models

from apps.core.models import TimeStampedModel
from apps.shipments.models import Shipment


class Notification(TimeStampedModel):
    """
    Outbox pattern: a row is written first, a background worker sends it and
    updates the status. Nothing sends synchronously from a request.
    """

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        TELEGRAM = "telegram", "Telegram"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    recipient = models.CharField(max_length=255, help_text="Phone number / chat id / email")
    template = models.CharField(max_length=50, help_text="tracking_link, out_for_delivery, delivered, ...")
    body = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    provider_message_id = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"{self.channel} -> {self.recipient} [{self.status}]"
