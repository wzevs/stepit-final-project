from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class CourierCompany(UUIDModel, TimeStampedModel):
    """The tenant. Every business record carries a FK to a company."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    legal_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    tracking_prefix = models.CharField(
        max_length=5,
        unique=True,
        help_text="Prefix for tracking numbers, e.g. GLX -> GLX-7K2M9Q",
    )
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name_plural = "courier companies"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class CompanyMembership(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        DISPATCHER = "dispatcher", "Dispatcher"
        VIEWER = "viewer", "Viewer"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_memberships"
    )
    company = models.ForeignKey(CourierCompany, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DISPATCHER)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("user", "company")]

    def __str__(self) -> str:
        return f"{self.user} @ {self.company} ({self.role})"
