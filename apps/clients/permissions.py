from rest_framework.permissions import BasePermission

from apps.integrations.models import ApiKey

from .access import resolve_client


class IsClientActor(BasePermission):
    message = "No active client access."

    def has_permission(self, request, view):
        client = resolve_client(request)
        if client is None:
            return False
        if isinstance(request.auth, ApiKey) and not client.api_enabled:
            self.message = "API access is not enabled for this client."
            return False
        request.client = client
        return True
