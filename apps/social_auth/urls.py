from django.urls import path

from .views import GoogleLoginView, YandexLoginView

urlpatterns = [
    path("google/", GoogleLoginView.as_view(), name="social-google-login"),
    path("yandex/", YandexLoginView.as_view(), name="social-yandex-login"),
]
