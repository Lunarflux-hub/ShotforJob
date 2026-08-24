from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import SocialAccount
from .serializers import GoogleLoginSerializer, YandexLoginSerializer
from .services.google import GoogleAuthError, verify_google_id_token
from .services.yandex import YandexAuthError, fetch_yandex_user_info

User = get_user_model()


def _issue_tokens_for_user(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _unique_username(base: str) -> str:
    username = base
    suffix = 1
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}{suffix}"
    return username


def _get_or_create_user_for_social(provider: str, provider_user_id: str, email: str | None, name: str | None):
    social_account = (
        SocialAccount.objects.filter(provider=provider, provider_user_id=provider_user_id)
        .select_related("user")
        .first()
    )
    if social_account:
        return social_account.user

    with transaction.atomic():
        # Если пользователь уже регистрировался обычным способом с таким же
        # email — привязываем соцаккаунт к нему, а не плодим дубликат.
        user = User.objects.filter(email=email).first() if email else None

        if not user:
            base_username = email.split("@")[0] if email else f"{provider}_{provider_user_id}"
            user = User.objects.create_user(
                username=_unique_username(base_username),
                email=email or "",
                first_name=(name or "")[:150],
            )
            # У пользователя, вошедшего только через OAuth, нет пароля в нашей
            # системе — явно помечаем это, чтобы он не мог залогиниться паролем.
            user.set_unusable_password()
            user.save(update_fields=["password"])

        SocialAccount.objects.create(
            user=user, provider=provider, provider_user_id=provider_user_id, email=email or ""
        )
        return user


class GoogleLoginView(APIView):
    """
    POST /api/auth/google/
    body: {"id_token": "<credential с фронтенда от Google Identity Services>"}
    Возвращает {"access", "refresh", "profile": {"name", "email", "picture"}}.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            profile = verify_google_id_token(serializer.validated_data["id_token"])
        except GoogleAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        user = _get_or_create_user_for_social(
            provider=SocialAccount.Provider.GOOGLE,
            provider_user_id=profile["provider_user_id"],
            email=profile.get("email"),
            name=profile.get("name"),
        )
        return Response(
            {
                **_issue_tokens_for_user(user),
                "profile": {
                    "name": profile.get("name") or profile.get("email"),
                    "email": profile.get("email"),
                    "picture": profile.get("picture"),
                },
            }
        )


class YandexLoginView(APIView):
    """
    POST /api/auth/yandex/
    body: {"access_token": "<OAuth-токен с фронтенда после implicit-флоу Yandex ID>"}
    Возвращает {"access", "refresh", "profile": {"name", "email", "picture"}}.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = YandexLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            profile = fetch_yandex_user_info(serializer.validated_data["access_token"])
        except YandexAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        user = _get_or_create_user_for_social(
            provider=SocialAccount.Provider.YANDEX,
            provider_user_id=profile["provider_user_id"],
            email=profile.get("email"),
            name=profile.get("name"),
        )
        return Response(
            {
                **_issue_tokens_for_user(user),
                "profile": {
                    "name": profile.get("name"),
                    "email": profile.get("email"),
                    "picture": profile.get("picture"),
                },
            }
        )