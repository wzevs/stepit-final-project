from django.conf import settings
from django.db import models

from apps.companies.models import CourierCompany
from apps.core.models import TimeStampedModel, UUIDModel


class CourierProfile(UUIDModel, TimeStampedModel):
    class VehicleType(models.TextChoices):
        FOOT = "foot", "On foot"
        BIKE = "bike", "Bicycle"
        MOTO = "moto", "Motorcycle"
        CAR = "car", "Car"
        VAN = "van", "Van"

    class Status(models.TextChoices):
        OFFLINE = "offline", "Offline"
        AVAILABLE = "available", "Available"
        BUSY = "busy", "Busy"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="courier_profile"
    )
    company = models.ForeignKey(CourierCompany, on_delete=models.PROTECT, related_name="couriers")
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices, default=VehicleType.CAR)
    vehicle_plate = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OFFLINE, db_index=True)
    is_active = models.BooleanField(default=True)

    # Denormalized last known position. Dispatcher map and public tracking
    # read from here instead of scanning CourierLocation.
    last_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.email} @ {self.company.name}"


class Device(TimeStampedModel):
    """
    A courier's work device (company-issued Android tablet/phone).
    Holds the FCM token for push notifications.
    """

    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    courier = models.ForeignKey(CourierProfile, on_delete=models.CASCADE, related_name="devices")
    platform = models.CharField(max_length=10, choices=Platform.choices, default=Platform.ANDROID)
    fcm_token = models.CharField(max_length=255, unique=True)
    device_id = models.CharField(max_length=100, blank=True, help_text="Hardware/installation id")
    model_name = models.CharField(max_length=100, blank=True)
    app_version = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.courier} / {self.model_name or self.platform}"
