from decimal import Decimal

from django.db import models

from apps.companies.models import CourierCompany
from apps.core.models import Address, TimeStampedModel


class City(models.Model):
    """A city the courier company delivers in. Shared reference data, not per shop."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "cities"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class District(models.Model):
    """A neighbourhood inside a city. Tariffs between districts hang off this row."""

    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="districts")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["city__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["city", "name"], name="uniq_district_name_per_city"),
        ]

    def __str__(self) -> str:
        return f"{self.city.name} · {self.name}"


class Warehouse(TimeStampedModel):
    """
    A company hub. A city warehouse covers the whole city (district is empty).
    A district warehouse sits in one neighbourhood of that city.
    """

    class Kind(models.TextChoices):
        CITY = "city", "ქალაქის საწყობი"
        DISTRICT = "district", "უბნის საწყობი"

    company = models.ForeignKey(CourierCompany, on_delete=models.CASCADE, related_name="warehouses")
    name = models.CharField(max_length=150)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="warehouses")
    district = models.ForeignKey(
        District, null=True, blank=True, on_delete=models.PROTECT, related_name="warehouses"
    )
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="+")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["city__name", "kind", "name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_warehouse_name_per_company"),
            models.CheckConstraint(
                condition=models.Q(kind="city", district__isnull=True)
                | models.Q(kind="district", district__isnull=False),
                name="warehouse_kind_matches_district",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Tariff(TimeStampedModel):
    """
    One price row. The kind decides which foreign keys are filled:

    standard — no places; the fallback price
    home     — no places; added when the parcel goes to the door
    city     — origin city and destination city
    district — origin district and destination district
    """

    class Kind(models.TextChoices):
        STANDARD = "standard", "სტანდარტული"
        HOME = "home", "სახლამდე მიტანა"
        CITY = "city", "ქალაქებს შორის"
        DISTRICT = "district", "უბნებს შორის"

    company = models.ForeignKey(CourierCompany, on_delete=models.CASCADE, related_name="tariffs")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    origin_city = models.ForeignKey(
        City, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    destination_city = models.ForeignKey(
        City, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    origin_district = models.ForeignKey(
        District, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    destination_district = models.ForeignKey(
        District, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name="tariff_price_non_negative"),
            models.CheckConstraint(
                condition=(
                    models.Q(kind__in=["standard", "home"])
                    & models.Q(
                        origin_city__isnull=True,
                        destination_city__isnull=True,
                        origin_district__isnull=True,
                        destination_district__isnull=True,
                    )
                )
                | (
                    models.Q(kind="city")
                    & models.Q(
                        origin_city__isnull=False,
                        destination_city__isnull=False,
                        origin_district__isnull=True,
                        destination_district__isnull=True,
                    )
                )
                | (
                    models.Q(kind="district")
                    & models.Q(
                        origin_district__isnull=False,
                        destination_district__isnull=False,
                        origin_city__isnull=True,
                        destination_city__isnull=True,
                    )
                ),
                name="tariff_shape_matches_kind",
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(kind="standard"),
                name="uniq_standard_tariff_per_company",
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=models.Q(kind="home"),
                name="uniq_home_tariff_per_company",
            ),
            models.UniqueConstraint(
                fields=["company", "origin_city", "destination_city"],
                condition=models.Q(kind="city"),
                name="uniq_city_pair_tariff",
            ),
            models.UniqueConstraint(
                fields=["company", "origin_district", "destination_district"],
                condition=models.Q(kind="district"),
                name="uniq_district_pair_tariff",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.price}"


class WeightBand(TimeStampedModel):
    """
    Extra price for a weight interval, added after the route and before home delivery.
    min_kg is included. max_kg is excluded. An empty max_kg means this band has no ceiling.
    """

    company = models.ForeignKey(CourierCompany, on_delete=models.CASCADE, related_name="weight_bands")
    min_kg = models.DecimalField(max_digits=7, decimal_places=3)
    max_kg = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    surcharge = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["min_kg"]
        constraints = [
            models.CheckConstraint(condition=models.Q(min_kg__gte=0), name="weight_band_min_non_negative"),
            models.CheckConstraint(
                condition=models.Q(surcharge__gte=0), name="weight_band_surcharge_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(max_kg__isnull=True) | models.Q(max_kg__gt=models.F("min_kg")),
                name="weight_band_max_above_min",
            ),
        ]

    def __str__(self) -> str:
        ceiling = f"{self.max_kg}" if self.max_kg is not None else "∞"
        return f"{self.min_kg}–{ceiling} კგ +{self.surcharge}"

    def covers(self, weight_kg: Decimal) -> bool:
        if weight_kg < self.min_kg:
            return False
        return self.max_kg is None or weight_kg < self.max_kg

    def overlaps(self, min_kg: Decimal, max_kg: Decimal | None) -> bool:
        ceiling = max_kg if max_kg is not None else Decimal("1000000")
        other = self.max_kg if self.max_kg is not None else Decimal("1000000")
        return min_kg < other and self.min_kg < ceiling
