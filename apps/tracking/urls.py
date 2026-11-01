from django.urls import path

from .views import PublicLiveView, PublicTrackingView

app_name = "tracking"

urlpatterns = [
    path("<str:token>/live/", PublicLiveView.as_view(), name="public-live"),
    path("<str:token>/", PublicTrackingView.as_view(), name="public"),
]
