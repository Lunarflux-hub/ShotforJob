"""
Проверка Google ID token, полученного на фронтенде через Google Identity
Services (https://accounts.google.com/gsi/client).

Фронт получает `credential` (это и есть подписанный Google ID token) и
отправляет его на бэкенд. Мы проверяем подпись и audience через официальную
библиотеку google-auth — она сама сверяет токен с публичными ключами Google.
"""
import logging

from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

logger = logging.getLogger(__name__)

VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(Exception):
    pass


def verify_google_id_token(token: str) -> dict:
    try:
        idinfo = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
        )
    except ValueError as exc:
        logger.warning("Невалидный Google ID token: %s", exc)
        raise GoogleAuthError("Невалидный или просроченный токен Google") from exc

    if idinfo.get("iss") not in VALID_ISSUERS:
        raise GoogleAuthError("Неверный issuer у токена Google")

    return {
        "provider_user_id": idinfo["sub"],
        "email": idinfo.get("email"),
        "email_verified": idinfo.get("email_verified", False),
        "name": idinfo.get("name", ""),
        "picture": idinfo.get("picture", ""),
    }
