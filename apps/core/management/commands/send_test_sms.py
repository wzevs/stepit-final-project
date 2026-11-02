from django.core.management.base import BaseCommand, CommandError

from apps.notifications.delivery import send_ubill_sms, sms_is_configured


class Command(BaseCommand):
    help = "Send one SMS via uBill so you can confirm the API key and brand."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Georgian mobile, e.g. 555123456 or 995555123456")

    def handle(self, *args, **options):
        if not sms_is_configured():
            raise CommandError(
                "uBill is not configured. Set UBILL_API_KEY and UBILL_BRAND_ID in .env, "
                "then restart the shell."
            )
        to = options["to"]
        provider_id = send_ubill_sms(to, "Galaxy Express: სატესტო SMS. თუ ეს მოგივიდათ, API მუშაობს.")
        self.stdout.write(self.style.SUCCESS(f"Sent test SMS to {to} (id={provider_id})"))
