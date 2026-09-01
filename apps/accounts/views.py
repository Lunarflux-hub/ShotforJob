from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import EmailTokenObtainPairSerializer, RegisterSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — регистрация по email+паролю (email = логин)."""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class EmailLoginView(TokenObtainPairView):
    """
    POST /api/auth/login/
    body: {"email": "...", "password": "..."}
    ТЕСТОВЫЙ вход по email/паролю для интеграции с платёжкой (взамен/вместе
    с OAuth2). Возвращает {"access", "refresh"} как и раньше.
    """

    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
