"""
Сохранение отзыва о генерации. Общая точка для веб-API
(apps.photos.views.OrderReviewView) и Telegram-бота
(apps.telegram_bot.bot.services.save_bot_review).
"""
from __future__ import annotations

from ..models import GeneratedResult, Order, OrderReview

# Карусель отзывов на главной показывается только когда есть хотя бы
# столько реальных одобренных отзывов — выдуманные отзывы не показываем.
LANDING_MIN_REVIEWS = 3

# Счётчик «N фото сгенерировано» на главной — только от этого порога:
# маленькое число работает против доверия, а не на него.
PHOTOS_COUNTER_MIN = 100


def mask_email(email: str) -> str:
    """keylong@gmail.com -> ke*****@gmail.com: звёздочек примерно столько,
    сколько скрыто символов (от 4 до 8), как у заглушек выше."""
    local, _, domain = (email or "").partition("@")
    if not local or not domain:
        return ""
    stars = min(max(len(local) - 2, 4), 8)
    return f"{local[:2]}{'*' * stars}@{domain}"


def landing_reviews(limit: int = 12) -> list[dict]:
    """Отзывы для карусели на главной: только одобренные в админке (is_public)
    реальные отзывы с комментарием, почта автора замаскирована. Меньше
    LANDING_MIN_REVIEWS — пустой список, блок на главной скрывается."""
    reviews = [
        {
            "text": review.comment,
            "email": mask_email(review.order.user.email if review.order.user_id else "") or "Пользователь Telegram",
            "rating": review.rating,
        }
        for review in OrderReview.objects.filter(is_public=True)
        .exclude(comment="")
        .select_related("order__user")[:limit]
    ]
    return reviews if len(reviews) >= LANDING_MIN_REVIEWS else []


def photos_generated_count() -> int | None:
    """Сколько фото сгенерировано (без заказов сотрудников — это тесты).
    None, если меньше PHOTOS_COUNTER_MIN — тогда счётчик на главной скрыт.
    Округляем вниз до десятков: «130+ фото»."""
    count = GeneratedResult.objects.exclude(order__user__is_staff=True).count()
    if count < PHOTOS_COUNTER_MIN:
        return None
    return count // 10 * 10


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
