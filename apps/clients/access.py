from apps.integrations.models import ApiKey


def resolve_client(request):
    """The shop this request acts for, or None when the caller has no access."""
    auth = getattr(request, "auth", None)
    if isinstance(auth, ApiKey):
        client = auth.client
        if client.is_active and client.company.is_active:
            return client
        return None

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None

    memberships = user.client_memberships.filter(
        is_active=True, client__is_active=True, client__company__is_active=True
    ).select_related("client", "client__company")

    params = getattr(request, "query_params", None)
    client_id = params.get("client") if params is not None else None
    if client_id:
        memberships = memberships.filter(client_id=client_id)
    membership = memberships.first()
    return membership.client if membership else None
