import secrets
import string

from django.conf import settings
from django.db import models

from apps.clients.models import Client, PickupPoint
from apps.companies.models import CourierCompany
from apps.core.models import Address, TimeStampedModel, UUIDModel
from apps.couriers.models import CourierProfile

# Uppercase letters + digits without the easily confused O/0/I/1.
_ALPHABET = (string.ascii_uppercase + string.digits).translate(str.maketrans("", "", "O0I1"))


def generate_tracking_number(prefix: str, length: int = 8) -> str:
    return f"{prefix}-{''.join(secrets.choice(_ALPHABET) for _ in range(length))}"


class Shipment(UUIDModel, TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending pickup"
        ASSIGNED = "assigned", "Assigned to courier"
        PICKED_UP = "picked_up", "Picked up"
        IN_TRANSIT = "in_transit", "In transit"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Delivery failed"
        RETURNED = "returned", "Returned to sender"
        CANCELLED = "cancelled", "Cancelled"

    class Source(models.TextChoices):
        API = "api", "API"
        MANUAL = "manual", "Manual (dashboard)"
        IMPORT = "import", "File import"

    class PaymentType(models.TextChoices):
        PREPAID = "prepaid", "Prepaid"
        COD = "cod", "Cash on delivery"

    # Ownership
    company = models.ForeignKey(CourierCompany, on_delete=models.PROTECT, related_name="shipments")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="shipments")
    courier = models.ForeignKey(
        CourierProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="shipments"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    # Identifiers
    tracking_number = models.CharField(max_length=20, unique=True, editable=False)
    external_id = models.CharField(
        max_length=100, blank=True, help_text="Client's own order id; used for API idempotency"
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)

    # Status
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    # From / to
    pickup_point = models.ForeignKey(
        PickupPoint, null=True, blank=True, on_delete=models.SET_NULL, related_name="shipments"
    )
    pickup_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="pickup_shipments")
    delivery_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="delivery_shipments")

    # Recipient (not a User)
    recipient_name = models.CharField(max_length=150)
    recipient_phone = models.CharField(max_length=20, db_index=True)
    recipient_email = models.EmailField(blank=True)

    # Parcel
    description = models.CharField(max_length=255, blank=True)
    weight_kg = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    dimensions_cm = models.CharField(max_length=30, blank=True, help_text="LxWxH, e.g. 30x20x10")
    declared_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.PREPAID)
    cod_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_fragile = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    # Timing
    scheduled_pickup_at = models.DateTimeField(null=True, blank=True)
    scheduled_delivery_date = models.DateField(null=True, blank=True, db_index=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    # Proof of delivery
    proof_photo = models.ImageField(upload_to="proofs/%Y/%m/", blank=True)
    proof_signature = models.ImageField(upload_to="signatures/%Y/%m/", blank=True)
    received_by = models.CharField(max_length=150, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    # Raw integration payload / extra client fields
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["client", "status"]),
            models.Index(fields=["courier", "status"]),
            models.Index(fields=["company", "scheduled_delivery_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "external_id"],
                condition=~models.Q(external_id=""),
                name="uniq_external_id_per_client",
            ),
            models.CheckConstraint(condition=models.Q(cod_amount__gte=0), name="cod_amount_non_negative"),
        ]

    def save(self, *args, **kwargs):
        if not self.tracking_number:
            self.tracking_number = self._unique_tracking_number()
        super().save(*args, **kwargs)

    def _unique_tracking_number(self) -> str:
        prefix = self.company.tracking_prefix
        for _ in range(10):
            candidate = generate_tracking_number(prefix)
            if not Shipment.objects.filter(tracking_number=candidate).exists():
                return candidate
        raise RuntimeError("Could not generate a unique tracking number")

    def __str__(self) -> str:
        return self.tracking_number

    @property
    def is_terminal(self) -> bool:
        return self.status in {self.Status.DELIVERED, self.Status.RETURNED, self.Status.CANCELLED}

    @property
    def is_live_trackable(self) -> bool:
        """Courier position is exposed to the recipient only while heading to them."""
        return self.status == self.Status.OUT_FOR_DELIVERY and self.courier_id is not None


class ShipmentEvent(TimeStampedModel):
    """
    Append-only history of status changes and other notable events.
    Billing and reporting will be built on top of this table.
    """

    class Kind(models.TextChoices):
        STATUS_CHANGE = "status_change", "Status change"
        ASSIGNED = "assigned", "Courier assigned"
        UNASSIGNED = "unassigned", "Courier unassigned"
        NOTE = "note", "Note"
        NOTIFICATION = "notification", "Notification sent"

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_public = models.BooleanField(default=True, help_text="Shown on the recipient tracking page")

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["shipment", "created_at"])]

    def __str__(self) -> str:
        return f"{self.shipment} {self.kind} {self.from_status}->{self.to_status}"
