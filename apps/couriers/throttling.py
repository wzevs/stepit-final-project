from rest_framework.throttling import SimpleRateThrottle


class CourierLocationThrottle(SimpleRateThrottle):
    scope = "courier_location"

    def get_cache_key(self, request, view):
        courier = getattr(request, "courier", None)
        if courier is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": str(courier.pk)}
