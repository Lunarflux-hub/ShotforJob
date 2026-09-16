"""
Уведомление пользователя в Telegram о результате генерации.

Вызывается напрямую из apps.photos.tasks.generate_photo_task (Celery-воркер),
а не через polling из процесса бота — так уведомление доходит даже если
контейнер бота в этот момент перезапускается: это просто HTTP-запрос к
Telegram Bot API, не завязанный на его long-polling соединение.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, **params) -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    url = _API_BASE.format(token=settings.TELEGRAM_BOT_TOKEN, method=method)
    try:
        resp = requests.post(url, data=params, timeout=15)
        if not resp.ok:
            logger.warning("Telegram API %s вернул %s: %s", method, resp.status_code, resp.text)
    except requests.RequestException:
        logger.exception("Не удалось вызвать Telegram API %s", method)


def notify_order_result(order) -> None:
    """
    Тихо ничего не делает, если у заказа нет привязанного TelegramProfile
    (значит заказ пришёл с сайта, а не из бота).
    """
    profile = getattr(order.user, "telegram_profile", None) if order.user_id else None
    if profile is None:
        return

    from apps.photos.models import Order  # локальный импорт — избегаем цикла apps

    if order.status == Order.Status.DONE:
        result = order.results.first()
        if result is None:
            _call("sendMessage", chat_id=profile.telegram_id, text="Готово, но результат не найден — обратитесь в поддержку.")
            return
        _call(
            "sendPhoto",
            chat_id=profile.telegram_id,
            photo=result.file_url,
            caption="✅ Ваше фото готово!",
        )
    elif order.status == Order.Status.FAILED:
        _call(
            "sendMessage",
            chat_id=profile.telegram_id,
            text=(
                "❌ Не удалось сгенерировать фото. "
                "Попробуйте создать заказ заново из меню бота."
            ),
        )
