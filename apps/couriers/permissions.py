from rest_framework.permissions import BasePermission

from .models import CourierProfile


class IsCourier(BasePermission):
    message = "Courier access required."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        profile = (
            CourierProfile.objects.filter(user=user, is_active=True, company__is_active=True)
            .select_related("user", "company")
            .first()
        )
        if profile is None:
            return False
        request.courier = profile
        return True
