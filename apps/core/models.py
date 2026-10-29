import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class Address(TimeStampedModel):
    """
    Shared address table used for pickup points, pickup/delivery addresses
    and billing addresses. Geo logic is isolated here so a later move to
    PostGIS only touches this model.
    """

    country = models.CharField(max_length=2, default="GE")
    city = models.CharField(max_length=100, db_index=True)
    line1 = models.CharField(max_length=255, help_text="Street and building number")
    line2 = models.CharField(max_length=255, blank=True, help_text="Entrance, floor, apartment")
    postal_code = models.CharField(max_length=20, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    google_place_id = models.CharField(max_length=255, blank=True)
    formatted = models.CharField(max_length=500, blank=True, help_text="Google formatted_address")
    notes = models.CharField(max_length=255, blank=True, help_text="e.g. 'call at the door'")

    class Meta:
        verbose_name_plural = "addresses"
        indexes = [models.Index(fields=["latitude", "longitude"])]

    def __str__(self) -> str:
        return self.formatted or f"{self.city}, {self.line1}"

    @property
    def is_geocoded(self) -> bool:
        return self.latitude is not None and self.longitude is not None
