"""
Recipient message templates. A company can override any of them via
CourierCompany.settings["message_templates"][<name>].

Georgian text is sent as Unicode SMS (70 chars per segment), so keep these short.
"""

from apps.shipments.models import Shipment

DEFAULT_TEMPLATES: dict[str, str] = {
    "tracking_link": "{company}: ამანათი {tracking_number} აღებულია. თვალი ადევნეთ: {url}",
    "out_for_delivery": "{company}: კურიერი გზაშია თქვენკენ. ამანათი {tracking_number}: {url}",
    "delivered": "{company}: ამანათი {tracking_number} ჩაბარდა. გმადლობთ!",
    "failed": "{company}: ამანათი {tracking_number} ვერ ჩაბარდა ({reason}). დაგიკავშირდებით.",
}


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def render(template: str, shipment: Shipment, **context) -> str:
    overrides = (shipment.company.settings or {}).get("message_templates", {})
    text = overrides.get(template) or DEFAULT_TEMPLATES[template]
    values = _SafeDict(
        company=shipment.company.name,
        tracking_number=shipment.tracking_number,
        recipient=shipment.recipient_name,
        reason=shipment.failure_reason,
        **context,
    )
    return text.format_map(values)
