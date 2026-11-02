from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

from apps.companies.live import live_couriers

from .models import TrackingToken
from .realtime import company_group, shipment_group
from .services import public_live_payload


class DispatcherLiveConsumer(JsonWebsocketConsumer):
    def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            self.close()
            return
        memberships = list(
            user.company_memberships.filter(is_active=True, company__is_active=True).select_related("company")
        )
        if not memberships:
            self.close()
            return
        session = self.scope.get("session") or {}
        wanted = session.get("manage_company_id")
        match = next((row for row in memberships if str(row.company_id) == wanted), None)
        membership = match or memberships[0]
        self.group_name = company_group(membership.company_id)
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()
        self.send_json(live_couriers(membership.company))

    def disconnect(self, code):
        if getattr(self, "group_name", None):
            async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)

    def live_update(self, event):
        self.send_json(event["payload"])


class PublicLiveConsumer(JsonWebsocketConsumer):
    def connect(self):
        token = self.scope["url_route"]["kwargs"]["token"]
        resolved = TrackingToken.resolve(token)
        if resolved is None:
            self.close()
            return
        self.group_name = shipment_group(resolved.shipment_id)
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()
        self.send_json(public_live_payload(resolved.shipment))

    def disconnect(self, code):
        if getattr(self, "group_name", None):
            async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)

    def live_update(self, event):
        self.send_json(event["payload"])
