from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
]
