from rest_framework.throttling import SimpleRateThrottle

from apps.integrations.models import ApiKey


class ClientApiThrottle(SimpleRateThrottle):
    scope = "client_api"

    def get_cache_key(self, request, view):
        if isinstance(getattr(request, "auth", None), ApiKey):
            ident = f"key:{request.auth.prefix}"
        elif request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}
