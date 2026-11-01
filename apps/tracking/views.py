from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from apps.shipments.labels import STATUS_KA

from .models import TrackingToken
from .services import public_live_payload

LIVE_THROTTLE_LIMIT = 30
LIVE_THROTTLE_WINDOW = 60


def _resolve(raw: str) -> TrackingToken | None:
    return TrackingToken.resolve(raw)


class PublicTrackingView(View):
    def get(self, request, token):
        resolved = _resolve(token)
        if resolved is None:
            return render(request, "public/track_missing.html", status=404)
        resolved.touch()
        shipment = resolved.shipment
        events = shipment.events.filter(is_public=True)
        return render(
            request,
            "public/track.html",
            {
                "shipment": shipment,
                "events": events,
                "status_ka": STATUS_KA,
                "token": token,
                "live": shipment.is_live_trackable,
            },
        )


class PublicLiveView(View):
    def get(self, request, token):
        if _throttled(request):
            return JsonResponse({"detail": "Too many requests"}, status=429)
        resolved = _resolve(token)
        if resolved is None:
            return JsonResponse({"detail": "Not found"}, status=404)
        return JsonResponse(public_live_payload(resolved.shipment))


def _throttled(request) -> bool:
    ident = request.META.get("REMOTE_ADDR") or "anon"
    key = f"throttle:public_tracking:{ident}"
    count = cache.get(key, 0)
    if count >= LIVE_THROTTLE_LIMIT:
        return True
    cache.set(key, count + 1, LIVE_THROTTLE_WINDOW)
    return False
