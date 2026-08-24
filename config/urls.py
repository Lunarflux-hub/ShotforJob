from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),  # оставил один раз
    path("api/auth/", include("apps.accounts.urls")),
    path("api/auth/", include("apps.social_auth.urls")),
    path("api/", include("apps.photos.urls")),
    path("api/", include("apps.support.urls")),
    path("api/billing/", include("apps.billing.urls")),
    path(
        "",
        TemplateView.as_view(
            template_name="index.html",
            extra_context={
                "google_client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "yandex_client_id": settings.YANDEX_OAUTH_CLIENT_ID,
            },
        ),
        name="home",
    ),
    path(
        "login/",
        TemplateView.as_view(
            template_name="login.html",
            extra_context={
                "google_client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "yandex_client_id": settings.YANDEX_OAUTH_CLIENT_ID,
            },
        ),
        name="login",
    ),
    path("workstation/", TemplateView.as_view(template_name="workstation.html"), name="workstation"),
    path("payment/", TemplateView.as_view(template_name="payment.html"), name="payment"),
    path("billing/success/", TemplateView.as_view(template_name="billing_success.html"), name="billing_success"),
    path("billing/fail/", TemplateView.as_view(template_name="billing_fail.html"), name="billing_fail"),
    path("billing/history/", TemplateView.as_view(template_name="billing_history.html"), name="billing_history"),
    path("results/", TemplateView.as_view(template_name="results.html"), name="results"),
    # ---------- НОВЫЙ МАРШРУТ ДЛЯ ПОЛИТИКИ ----------
    path("policy/", TemplateView.as_view(template_name="policy.html"), name="policy"),
    # ---------- НОВЫЙ МАРШРУТ ДЛЯ СТРАНИЦЫ ПОДДЕРЖКИ ----------
    path("support/", TemplateView.as_view(template_name="support.html"), name="support"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)