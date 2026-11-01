from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import GateLoginView, HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("login/", GateLoginView.as_view(), name="gate-login"),
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("dashboard/", include("apps.clients.dashboard_urls")),
    path("manage/", include("apps.companies.panel_urls")),
    path("courier/", include("apps.couriers.portal_urls")),
    path("t/", include("apps.tracking.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
