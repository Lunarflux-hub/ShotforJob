"""
Проверка Yandex ID access_token, полученного на фронтенде через implicit-флоу
OAuth (https://oauth.yandex.ru/authorize?response_type=token&...).

У Yandex OAuth нет отдельного эндпоинта "проверить токен" — вместо этого мы
запрашиваем данные пользователя по токену: если токен валиден, Yandex вернёт
профиль, если нет — 401. Это и служит проверкой подлинности токена.
"""
import logging

import requests

logger = logging.getLogger(__name__)

YANDEX_USER_INFO_URL = "https://login.yandex.ru/info"


class YandexAuthError(Exception):
    pass


def fetch_yandex_user_info(access_token: str) -> dict:
    try:
        resp = requests.get(
            YANDEX_USER_INFO_URL,
            params={"format": "json"},
            headers={"Authorization": f"OAuth {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Ошибка проверки токена Yandex ID: %s", exc)
        raise YandexAuthError("Невалидный или просроченный токен Yandex ID") from exc

    data = resp.json()

    avatar_id = data.get("default_avatar_id")
    picture = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200" if avatar_id else ""

    return {
        "provider_user_id": str(data["id"]),
        "email": data.get("default_email") or next(iter(data.get("emails") or []), None),
        "login": data.get("login"),
        "name": data.get("real_name") or data.get("display_name") or data.get("login"),
        "picture": picture,
    }
