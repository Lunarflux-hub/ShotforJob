"""
Сохранение отзыва о генерации. Общая точка для веб-API
(apps.photos.views.OrderReviewView) и Telegram-бота
(apps.telegram_bot.bot.services.save_bot_review).
"""
from __future__ import annotations

from ..models import Order, OrderReview

# Заглушки для карусели на главной, пока опубликованных отзывов мало. Почты
# выдуманные и уже замаскированные — реальные адреса клиентов под
# ненаписанными ими отзывами показывать нельзя.
PLACEHOLDER_REVIEWS = [
    {"text": "Сделала фото на резюме за пять минут, выглядит как из студии. Уже отправила в три компании!", "email": "an****@gmail.com", "rating": 5},
    {"text": "Нужно было срочно фото на пропуск, а в фотосалон не успевал. Результат отличный, спасибо", "email": "dm********@yandex.ru", "rating": 5},
    {"text": "Деловой стиль получился очень естественным — коллеги не поверили, что это нейросеть.", "email": "ek*****@mail.ru", "rating": 4},
    {"text": "Удобно, что можно выбрать одежду и фон. С первого раза чуть не то, со второго идеально", "email": "se******@gmail.com", "rating": 4},
    {"text": "Обновила аватарку в LinkedIn, стало намного солиднее. Рекомендую!", "email": "ol****@yandex.ru", "rating": 5},
    {"text": "Неплохо, но волосы вышли слишком гладкими и фон пришлось перегенерировать. За свои деньги норм", "email": "ma*******@rambler.ru", "rating": 3},
    {"text": "Быстро и недорого. Фото на документы приняли без вопросов.", "email": "iv*****@mail.ru", "rating": 5},
    {"text": "Хороший результат, только пиджак немного не по размеру сел. В целом доволен", "email": "al********@outlook.com", "rating": 4},
    {"text": "Фото для портфолио вышло живым, без пластикового эффекта — приятно удивлена.", "email": "vi****@bk.ru", "rating": 4},
    {"text": "Сделал себе и жене фото на визу, всё приняли с первого раза", "email": "ro*******@gmail.com", "rating": 5},
]

LANDING_MIN_REVIEWS = len(PLACEHOLDER_REVIEWS)


def mask_email(email: str) -> str:
    """keylong@gmail.com -> ke*****@gmail.com: звёздочек примерно столько,
    сколько скрыто символов (от 4 до 8), как у заглушек выше."""
    local, _, domain = (email or "").partition("@")
    if not local or not domain:
        return ""
    stars = min(max(len(local) - 2, 4), 8)
    return f"{local[:2]}{'*' * stars}@{domain}"


def landing_reviews(limit: int = 12) -> list[dict]:
    """Отзывы для карусели на главной: опубликованные в админке (is_public),
    с замаскированной почтой автора; если их меньше LANDING_MIN_REVIEWS —
    добиваем заглушками."""
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
    if len(reviews) < LANDING_MIN_REVIEWS:
        reviews += PLACEHOLDER_REVIEWS[: LANDING_MIN_REVIEWS - len(reviews)]
    return reviews


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
