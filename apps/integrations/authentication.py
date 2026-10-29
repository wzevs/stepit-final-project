from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import ApiKey


class ApiKeyAuthentication(BaseAuthentication):
    """
    Authenticates a shop's own software via the X-API-Key header.
    No header means "not this scheme" so JWT or session can still run.
    A present but unknown key is a hard failure.
    """

    header = "X-API-Key"

    def authenticate(self, request):
        raw = request.headers.get(self.header)
        if not raw:
            return None
        key = ApiKey.resolve(raw.strip())
        if key is None:
            raise AuthenticationFailed("Invalid API key.")
        ApiKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return (AnonymousUser(), key)

    def authenticate_header(self, request):
        return "ApiKey"
