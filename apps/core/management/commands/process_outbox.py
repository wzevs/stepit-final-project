from django.core.management.base import BaseCommand

from apps.integrations.delivery import process_webhooks
from apps.notifications.delivery import process_notifications


class Command(BaseCommand):
    help = "Send queued SMS/email notifications and POST pending webhooks."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Max rows per queue in one pass")

    def handle(self, *args, **options):
        limit = options["limit"]
        notes = process_notifications(limit=limit)
        hooks = process_webhooks(limit=limit)
        self.stdout.write(
            "notifications sent={sent} failed={failed} skipped={skipped}".format(**notes)
        )
        self.stdout.write("webhooks sent={sent} failed={failed} skipped={skipped}".format(**hooks))
