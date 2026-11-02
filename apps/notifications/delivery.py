"""
Deliver queued Notification rows. The request path only writes the outbox;
this module is what actually sends (SMTP email, uBill SMS).
"""

import json
import logging
import re
import socket
from contextlib import contextmanager
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
_URL = re.compile(r"https?://[^\s]+")
_DIGITS = re.compile(r"\D+")


def email_is_configured() -> bool:
    return settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")


def sms_is_configured() -> bool:
    return bool(settings.UBILL_API_KEY and settings.UBILL_BRAND_ID)


@contextmanager
def _force_ipv4():
    """uBill allowlists IPv4; Windows otherwise connects from IPv6 and gets 403."""
    original = socket.getaddrinfo

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only
    try:
        yield
    finally:
        socket.getaddrinfo = original


def process_notifications(limit: int = 50) -> dict:
    """Send a batch of queued messages. Returns counts for the management command."""
    sent = failed = skipped = 0
    ids = list(
        Notification.objects.filter(status=Notification.Status.QUEUED)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    for pk in ids:
        result = deliver_notification(pk)
        if result == "sent":
            sent += 1
        elif result == "failed":
            failed += 1
        else:
            skipped += 1
    return {"sent": sent, "failed": failed, "skipped": skipped}


def deliver_notification(pk: int) -> str:
    with transaction.atomic():
        note = (
            Notification.objects.select_for_update()
            .select_related("shipment", "shipment__company")
            .get(pk=pk)
        )
        if note.status != Notification.Status.QUEUED:
            return "skipped"
        note.attempts += 1
        note.save(update_fields=["attempts", "updated_at"])

    try:
        provider_id = _send(note)
    except Exception as exc:
        with transaction.atomic():
            locked = Notification.objects.select_for_update().get(pk=pk)
            locked.error = str(exc)[:2000]
            if locked.attempts >= MAX_ATTEMPTS:
                locked.status = Notification.Status.FAILED
            locked.save(update_fields=["error", "status", "updated_at"])
        logger.warning("Notification %s attempt failed: %s", pk, exc)
        return "failed"

    with transaction.atomic():
        locked = Notification.objects.select_for_update().get(pk=pk)
        locked.status = Notification.Status.SENT
        locked.sent_at = timezone.now()
        locked.error = ""
        locked.provider_message_id = provider_id
        locked.save(
            update_fields=["status", "sent_at", "error", "provider_message_id", "updated_at"]
        )
    return "sent"


def _send(note: Notification) -> str:
    if note.channel == Notification.Channel.EMAIL:
        _send_email(note)
        return "email"
    if note.channel == Notification.Channel.SMS:
        if sms_is_configured():
            return send_ubill_sms(note.recipient, note.body)
        logger.info("SMS to %s: %s", note.recipient, note.body)
        return "console-sms"
    raise ValueError(f"Unknown channel {note.channel}")


def _send_email(note: Notification) -> None:
    subject = f"{note.shipment.company.name}: {note.shipment.tracking_number}"
    urls = _URL.findall(note.body)
    link = urls[0].rstrip(".,)") if urls else ""
    html = f"<p>{escape(note.body)}</p>"
    if link:
        html += (
            f'<p><a href="{escape(link, quote=True)}">'
            "რუკის გახსნა — კურიერის ყურება</a></p>"
        )
    message = EmailMultiAlternatives(
        subject=subject,
        body=note.body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[note.recipient],
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=False)


def georgian_msisdn(raw: str) -> str:
    digits = _DIGITS.sub("", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 9 and digits.startswith("5"):
        digits = "995" + digits
    if not (len(digits) == 12 and digits.startswith("995")):
        raise ValueError(f"Not a Georgian mobile number: {raw}")
    return digits


def send_ubill_sms(phone: str, text: str) -> str:
    """GET one SMS through uBill. Returns their sms id (or a fallback token)."""
    prefix = settings.SMS_BODY_PREFIX
    if prefix and not text.startswith(prefix):
        text = f"{prefix}{text}"
    query = urlencode(
        {
            "key": settings.UBILL_API_KEY,
            "brandID": settings.UBILL_BRAND_ID,
            "numbers": georgian_msisdn(phone),
            "text": text,
        }
    )
    request = Request(
        f"{settings.UBILL_API_URL}/v1/sms/send?{query}",
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with _force_ipv4():
            with urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode() or "{}")
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"uBill HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"uBill unreachable: {exc.reason}") from exc

    status = body.get("statusID")
    if status not in (0, "0"):
        raise RuntimeError(f"uBill rejected SMS (statusID={status}): {body}")
    sms_id = body.get("smsID") or (body.get("data") or {}).get("smsID")
    return str(sms_id or "ubill")
