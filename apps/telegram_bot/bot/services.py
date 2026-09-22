"""
Синхронные функции с бизнес-логикой бота. Вызываются из async-хендлеров
через asgiref.sync.sync_to_async — сами по себе остаются обычным
синхронным Django-кодом, чтобы 1:1 переиспользовать существующие
apps.billing.services / apps.photos.tasks, как это делает apps.photos.views.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import validate_email
from django.db import transaction

from apps.billing.models import GenerationPackage
from apps.billing.services import (
    InsufficientBalanceError,
    base_amount_for,
    create_topup_payment,
    get_balance,
    get_payment_status,
    make_pay_link,
    spend_generation,
)
from apps.photos.models import Order, PhotoStyle, UploadedPhoto
from apps.photos.services import storage
from apps.photos.services.reviews import save_review
from apps.photos.tasks import generate_photo_task
from apps.support.serializers import SupportTicketCreateSerializer
from apps.support.tasks import send_support_ticket_email

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


def save_bot_review(user, order_id, *, rating: int | None = None, comment: str | None = None) -> int | None:
    """Сохраняет оценку/комментарий к готовому заказу пользователя. Возвращает
    итоговую оценку или None, если заказ не найден (чужой/не готов)."""
    order = Order.objects.filter(id=order_id, user=user, status=Order.Status.DONE).first()
    if order is None:
        return None
    if rating is None and not hasattr(order, "review"):
        return None  # комментарий без оценки сохранять не к чему
    review = save_review(order, rating=rating, comment=comment, source="telegram")
    return review.rating


def get_user_balance(user) -> int:
    return get_balance(user)


@dataclass
class SetEmailResult:
    ok: bool
    error: str | None = None  # "invalid" | "taken"


def set_user_email(user, raw_email: str) -> SetEmailResult:
    email = (raw_email or "").strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return SetEmailResult(ok=False, error="invalid")

    if User.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
        return SetEmailResult(ok=False, error="taken")

    user.email = email
    user.save(update_fields=["email"])
    return SetEmailResult(ok=True)


@dataclass
class ProfileStats:
    email: str
    balance: int
    orders_total: int
    orders_done: int
    member_since: datetime.datetime


def get_profile_stats(user, profile: TelegramProfile) -> ProfileStats:
    orders = Order.objects.filter(user=user)
    return ProfileStats(
        email=user.email or "",
        balance=get_balance(user),
        orders_total=orders.count(),
        orders_done=orders.filter(status=Order.Status.DONE).count(),
        member_since=profile.created_at,
    )


@dataclass
class SupportTicketResult:
    ok: bool
    errors: dict | None = None


@dataclass
class TariffOption:
    id: int
    title: str
    price: Decimal
    generations: int
    is_promo: bool  # спеццена первой покупки


def list_tariffs(user) -> list[TariffOption]:
    options = []
    for package in GenerationPackage.objects.filter(is_active=True):
        amount = base_amount_for(package, user)
        options.append(
            TariffOption(
                id=package.id,
                title=package.title,
                price=amount,
                generations=package.generations,
                is_promo=amount != package.price,
            )
        )
    return options


@dataclass
class CreatePaymentResult:
    payment_id: int | None
    pay_url: str | None
    amount: Decimal | None = None
    generations: int | None = None
    error: str | None = None  # "invalid_package"


def create_bot_payment(user, package_id: int) -> CreatePaymentResult:
    try:
        package = GenerationPackage.objects.get(id=package_id, is_active=True)
    except GenerationPackage.DoesNotExist:
        return CreatePaymentResult(payment_id=None, pay_url=None, error="invalid_package")

    payment = create_topup_payment(user, package)
    return CreatePaymentResult(
        payment_id=payment.id,
        pay_url=make_pay_link(payment),
        amount=payment.amount,
        generations=payment.generations_granted,
    )


def get_bot_payment_status(user, payment_id: int) -> str | None:
    return get_payment_status(user, payment_id)


def create_support_ticket(email: str, message: str) -> SupportTicketResult:
    """Переиспользует ту же валидацию, что и веб-форма /support (см.
    apps.support.views.SupportTicketCreateView)."""
    serializer = SupportTicketCreateSerializer(data={"email": email, "message": message})
    if not serializer.is_valid():
        return SupportTicketResult(ok=False, errors=serializer.errors)

    ticket = serializer.save(ip_address=None)
    send_support_ticket_email.delay(str(ticket.id))
    return SupportTicketResult(ok=True)
