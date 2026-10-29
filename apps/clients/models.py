from django.conf import settings
from django.db import models

from apps.companies.models import CourierCompany
from apps.core.models import Address, TimeStampedModel, UUIDModel


class Client(UUIDModel, TimeStampedModel):
    """A shop or warehouse that is a customer of a specific courier company."""

    company = models.ForeignKey(CourierCompany, on_delete=models.PROTECT, related_name="clients")
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=30, help_text="Company-internal client code")
    contact_name = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    billing_address = models.ForeignKey(
        Address, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_active = models.BooleanField(default=True)
    api_enabled = models.BooleanField(
        default=False, help_text="Client has its own software and integrates via API"
    )

    class Meta:
        unique_together = [("company", "code")]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.company.name})"


class PickupPoint(TimeStampedModel):
    """A client's branch/warehouse where couriers pick parcels up."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="pickup_points")
    name = models.CharField(max_length=150)
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="+")
    contact_phone = models.CharField(max_length=20, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client"],
                condition=models.Q(is_default=True),
                name="uniq_default_pickup_per_client",
            )
        ]

    def __str__(self) -> str:
        return f"{self.client.name} / {self.name}"


class ClientMembership(TimeStampedModel):
    class Role(models.TextChoices):
        MANAGER = "manager", "Manager"
        OPERATOR = "operator", "Operator"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="client_memberships"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OPERATOR)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("user", "client")]

    def __str__(self) -> str:
        return f"{self.user} @ {self.client} ({self.role})"
