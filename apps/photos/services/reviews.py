"""
Сохранение отзыва о генерации. Общая точка для веб-API
(apps.photos.views.OrderReviewView) и Telegram-бота
(apps.telegram_bot.bot.services.save_bot_review).
"""
from __future__ import annotations

from ..models import Order, OrderReview


def save_review(order: Order, *, rating: int | None = None, comment: str | None = None, source: str) -> OrderReview:
    """
    Создаёт или обновляет отзыв на заказ. None в rating/comment означает
    «не менять» — так бот может сначала сохранить оценку по нажатию на
    звезду, а комментарий дописать следующим сообщением.
    """
    defaults = {"source": source}
    if rating is not None:
        defaults["rating"] = rating
    if comment is not None:
        defaults["comment"] = comment.strip()

    review, _ = OrderReview.objects.update_or_create(order=order, defaults=defaults)
    return review
