"""POST queued webhook deliveries. Signing matches apps.integrations.services."""

import logging
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from .models import WebhookDelivery
from .services import serialize_payload, sign_payload

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
TIMEOUT_SEC = 10
BACKOFF = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=6),
)


def process_webhooks(limit: int = 50) -> dict:
    now = timezone.now()
    sent = failed = skipped = 0
    ids = list(
        WebhookDelivery.objects.filter(
            delivered_at__isnull=True, next_retry_at__isnull=False, next_retry_at__lte=now
        )
        .order_by("next_retry_at")
        .values_list("pk", flat=True)[:limit]
    )
    for pk in ids:
        result = deliver_webhook(pk)
        if result == "sent":
            sent += 1
        elif result == "failed":
            failed += 1
        else:
            skipped += 1
    return {"sent": sent, "failed": failed, "skipped": skipped}


def deliver_webhook(pk: int) -> str:
    with transaction.atomic():
        row = WebhookDelivery.objects.select_for_update().select_related("webhook").get(pk=pk)
        if row.delivered_at is not None:
            return "skipped"
        if not row.webhook.is_active:
            row.next_retry_at = None
            row.response_body = "Webhook disabled"
            row.attempts += 1
            row.save(update_fields=["next_retry_at", "response_body", "attempts"])
            return "skipped"

        body = serialize_payload(row.payload)
        request = Request(
            row.webhook.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Signature": sign_payload(row.webhook.secret, body),
                "User-Agent": "GalaxyExpress-Webhook/1.0",
            },
        )
        row.attempts += 1
        try:
            with urlopen(request, timeout=TIMEOUT_SEC) as response:
                status = response.getcode()
                text = response.read(2048).decode("utf-8", errors="replace")
        except HTTPError as exc:
            status = exc.code
            text = (exc.read(2048) or b"").decode("utf-8", errors="replace")
            _mark_retry(row, status, text)
            return "failed"
        except (URLError, TimeoutError, OSError) as exc:
            _mark_retry(row, None, str(exc)[:2000])
            return "failed"

        row.response_status = status
        row.response_body = text[:2000]
        if 200 <= status < 300:
            row.delivered_at = timezone.now()
            row.next_retry_at = None
            row.save(
                update_fields=[
                    "attempts",
                    "response_status",
                    "response_body",
                    "delivered_at",
                    "next_retry_at",
                ]
            )
            return "sent"
        _mark_retry(row, status, text)
        return "failed"


def _mark_retry(row: WebhookDelivery, status: int | None, text: str) -> None:
    row.response_status = status
    row.response_body = text[:2000]
    if row.attempts >= MAX_ATTEMPTS:
        row.next_retry_at = None
        logger.warning("Webhook delivery %s given up after %s attempts", row.pk, row.attempts)
    else:
        delay = BACKOFF[min(row.attempts - 1, len(BACKOFF) - 1)]
        row.next_retry_at = timezone.now() + delay
    row.save(update_fields=["attempts", "response_status", "response_body", "next_retry_at"])
