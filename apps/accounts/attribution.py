"""
Атрибуция регистраций: UTM-метки и yclid из cookie sfj_attr (её пишет JS в
templates/base.html при заходе на сайт по размеченной ссылке) сохраняются в
UserAcquisition при регистрации и копируются в Payment при создании платежа.
"""
from __future__ import annotations

import json
from urllib.parse import unquote

from .models import ATTRIBUTION_FIELDS, UserAcquisition

ATTR_COOKIE = "sfj_attr"
_LIMITS = {"utm_source": 100, "utm_medium": 100, "yclid": 100, "referrer": 500, "landing_page": 500}


def _from_cookie(request) -> dict:
    raw = request.COOKIES.get(ATTR_COOKIE)
    if not raw:
        return {}
    try:
        data = json.loads(unquote(raw))
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    keys = ATTRIBUTION_FIELDS + ("referrer", "landing_page")
    return {k: str(data[k])[: _LIMITS.get(k, 200)] for k in keys if data.get(k)}


def capture_for_new_user(request, user) -> None:
    """Вызывается только для только что созданного пользователя — у старых
    аккаунтов источник регистрации уже неизвестен, и приписывать их текущей
    кампании было бы неверно."""
    data = _from_cookie(request)
    UserAcquisition.objects.get_or_create(user=user, defaults=data)


def fields_for_payment(user) -> dict:
    """UTM/yclid регистрации пользователя — для копирования в Payment."""
    acquisition = UserAcquisition.objects.filter(user=user).first()
    if acquisition is None:
        return {}
    return {f: getattr(acquisition, f) for f in ATTRIBUTION_FIELDS}
