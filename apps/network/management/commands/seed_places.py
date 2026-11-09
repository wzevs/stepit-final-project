from django.core.management.base import BaseCommand

from apps.network.models import City, District
from apps.network.seed import load_places


class Command(BaseCommand):
    help = "Insert Georgian cities and districts used by warehouses and tariffs."

    def handle(self, *args, **options):
        before = District.objects.count()
        load_places(City, District)
        added = District.objects.count() - before
        self.stdout.write(self.style.SUCCESS(f"ქალაქები მზადაა. ახალი უბანი: {added}"))
