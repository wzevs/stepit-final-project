from django.urls import path

from .consumers import DispatcherLiveConsumer, PublicLiveConsumer

websocket_urlpatterns = [
    path("ws/manage/live/", DispatcherLiveConsumer.as_asgi()),
    path("ws/t/<str:token>/live/", PublicLiveConsumer.as_asgi()),
]
