import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.couriers.models import CourierProfile
from apps.shipments.models import Shipment


class CourierLocation(models.Model):
    """
    High-volume append-only table. BigAutoField PK, no auto_now_add so that
    bulk_create works with explicit timestamps. Can be partitioned by
    recorded_at on PostgreSQL later.
    """

    id = models.BigAutoField(primary_key=True)
    courier = models.ForeignKey(CourierProfile, on_delete=models.CASCADE, related_name="locations")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = models.FloatField(null=True, blank=True)
    speed_mps = models.FloatField(null=True, blank=True)
    heading_deg = models.FloatField(null=True, blank=True)
    battery_pct = models.PositiveSmallIntegerField(null=True, blank=True)
    recorded_at = models.DateTimeField(help_text="Device time of the GPS fix")
    received_at = models.DateTimeField(default=timezone.now, help_text="Server time")

    class Meta:
        indexes = [models.Index(fields=["courier", "-recorded_at"])]
        get_latest_by = "recorded_at"

    def __str__(self) -> str:
        return f"{self.courier_id} @ {self.latitude},{self.longitude} ({self.recorded_at:%H:%M:%S})"


class TrackingToken(TimeStampedModel):
    """
    Public tracking-link token. Only a SHA-256 hash is stored, so a database
    leak does not leak the links. FK (not OneToOne) so a re-sent link revokes
    the previous one and issues a fresh token.
    """

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="tracking_tokens")
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    access_count = models.PositiveIntegerField(default=0)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    sent_via = models.CharField(max_length=20, blank=True, help_text="sms / telegram / email")

    class Meta:
        ordering = ["-created_at"]

    @staticmethod
    def hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(
        cls, shipment: Shipment, ttl_days: int | None = None, sent_via: str = ""
    ) -> tuple["TrackingToken", str]:
        """
        Revoke any active tokens for the shipment and create a new one.
        Returns (token_obj, raw_token). The raw token exists only in this
        return value; put it in the URL and never persist it.
        """
        ttl = ttl_days if ttl_days is not None else settings.TRACKING_TOKEN_TTL_DAYS
        cls.objects.filter(shipment=shipment, revoked_at__isnull=True).update(revoked_at=timezone.now())
        raw = secrets.token_urlsafe(32)
        obj = cls.objects.create(
            shipment=shipment,
            token_hash=cls.hash_token(raw),
            expires_at=timezone.now() + timedelta(days=ttl),
            sent_via=sent_via,
        )
        return obj, raw

    @classmethod
    def resolve(cls, raw: str) -> "TrackingToken | None":
        try:
            token = cls.objects.select_related("shipment", "shipment__courier").get(
                token_hash=cls.hash_token(raw)
            )
        except cls.DoesNotExist:
            return None
        return token if token.is_valid else None

    @property
    def is_valid(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()

    def touch(self) -> None:
        type(self).objects.filter(pk=self.pk).update(
            access_count=models.F("access_count") + 1, last_accessed_at=timezone.now()
        )

    def __str__(self) -> str:
        return f"token for {self.shipment} (valid={self.is_valid})"
