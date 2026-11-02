from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.delivery import email_is_configured


class Command(BaseCommand):
    help = "Send a one-line test message so you can confirm SMTP."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Destination email address")

    def handle(self, *args, **options):
        if not email_is_configured():
            raise CommandError(
                "SMTP is not configured. Set EMAIL_HOST, EMAIL_HOST_USER and "
                "EMAIL_HOST_PASSWORD in .env, then restart the server."
            )
        to = options["to"]
        send_mail(
            subject="Galaxy Express: test",
            message="თუ ეს წერილი მოგივიდათ, SMTP მუშაობს.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Sent test email to {to} via {settings.EMAIL_HOST}"))
