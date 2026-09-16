"""
Синхронные функции с бизнес-логикой бота. Вызываются из async-хендлеров
через asgiref.sync.sync_to_async — сами по себе остаются обычным
синхронным Django-кодом, чтобы 1:1 переиспользовать существующие
apps.billing.services / apps.photos.tasks, как это делает apps.photos.views.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction

from apps.billing.services import InsufficientBalanceError, get_balance, spend_generation
from apps.photos.models import Order, PhotoStyle, UploadedPhoto
from apps.photos.services import storage
from apps.photos.tasks import generate_photo_task

from ..models import TelegramProfile

User = get_user_model()


def get_or_create_profile(telegram_id: int, telegram_username: str) -> TelegramProfile:
    profile = TelegramProfile.objects.select_related("user").filter(telegram_id=telegram_id).first()
    if profile:
        return profile

    with transaction.atomic():
        user = User.objects.create(username=f"tg_{telegram_id}")
        user.set_unusable_password()
        user.save(update_fields=["password"])
        profile = TelegramProfile.objects.create(
            user=user,
            telegram_id=telegram_id,
            telegram_username=telegram_username or "",
        )
    return profile


def list_active_styles() -> list[PhotoStyle]:
    return list(PhotoStyle.objects.filter(is_active=True).order_by("sort_order", "id"))


def get_style(style_id: int) -> PhotoStyle | None:
    return PhotoStyle.objects.filter(id=style_id, is_active=True).first()


@dataclass
class NewOrderPhoto:
    filename: str
    data: bytes


@dataclass
class CreateOrderResult:
    order: Order | None
    error: str | None = None
    balance: int | None = None


def create_order_from_bot(
    *,
    user,
    style: PhotoStyle,
    clothing: str,
    background_type: str,
    background_color: str,
    background_image: NewOrderPhoto | None,
    photos: list[NewOrderPhoto],
) -> CreateOrderResult:
    """Тот же паттерн, что apps.photos.views.OrderCreateView.post."""
    try:
        with transaction.atomic():
            order = Order.objects.create(
                user=user,
                style=style,
                status=Order.Status.PENDING,
                clothing=clothing,
                background_type=background_type,
                background_color=background_color,
                background_image=(
                    ContentFile(background_image.data, name=background_image.filename)
                    if background_image
                    else None
                ),
            )
            spend_generation(user, order=order)

            for photo in photos:
                UploadedPhoto.objects.create(
                    order=order, image=ContentFile(photo.data, name=photo.filename)
                )
    except InsufficientBalanceError as exc:
        return CreateOrderResult(order=None, error="insufficient_balance", balance=exc.balance)

    generate_photo_task.delay(str(order.id))
    return CreateOrderResult(order=order)


def get_recent_orders(user, limit: int = 10) -> list[Order]:
    return list(
        Order.objects.filter(user=user).select_related("style").order_by("-created_at")[:limit]
    )


def get_order_photo_url(user, order_id) -> str | None:
    order = (
        Order.objects.filter(id=order_id, user=user, status=Order.Status.DONE)
        .prefetch_related("results")
        .first()
    )
    if order is None:
        return None
    result = order.results.first()
    if result is None:
        return None
    return storage.generate_presigned_url(result.s3_key)


def get_user_balance(user) -> int:
    return get_balance(user)
