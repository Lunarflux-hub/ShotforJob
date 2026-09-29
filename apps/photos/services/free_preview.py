"""
Бесплатное превью: первая генерация для аккаунта, который ни разу не платил
и ничего не генерировал, — без списания с баланса. Результат показывается
копией ~512px с водяным знаком; оригинал в HD открывается за 1 генерацию
(«Скачать в HD», см. apps/photos/views.ResultUnlockView), в том числе
автоматически после оплаты (Payment.unlock_result).

Только сайт: в Telegram-боте превью пока не выдаётся (решение продукта —
сначала посмотреть стоимость и абуз), но бот тоже отдаёт только delivery_key.
"""
from __future__ import annotations

import io
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps

from apps.billing.models import Payment
from apps.billing.services import spend_generation

from ..models import GeneratedResult, Order

IP_LIMIT = 2  # бесплатных превью с одного IP
IP_WINDOW = timedelta(days=30)
PREVIEW_MAX_SIDE = 512
WATERMARK_TEXT = "ShotForJob"


def client_ip(request) -> str | None:
    """Настоящий IP клиента. X-Real-IP выставляет nginx из $remote_addr —
    клиент его не подделает, в отличие от первого адреса в X-Forwarded-For."""
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or None


def _is_verified(user) -> bool:
    """На сайте вход только через Google/Яндекс ID — почту подтвердил провайдер.
    Аккаунт без соцсети (например, созданный вручную в админке) — не в счёт."""
    return user.social_accounts.exists() or hasattr(user, "telegram_profile")


def eligibility(user, ip: str | None) -> str | None:
    """None — превью положено; иначе код причины отказа.
    Вызывать под блокировкой баланса пользователя (см. views.OrderCreateView),
    чтобы два параллельных запроса не получили два бесплатных превью."""
    if not user.is_authenticated or not _is_verified(user):
        return "not_verified"
    if Payment.objects.filter(user=user, status=Payment.Status.PAID).exists():
        return "already_paid"
    # «Ничего не генерировал»: неудачное бесплатное превью шанс не сжигает
    previous = Order.objects.filter(user=user).exclude(is_free_preview=True, status=Order.Status.FAILED)
    if previous.exists():
        return "already_generated"
    if ip:
        recent_from_ip = (
            Order.objects.filter(is_free_preview=True, client_ip=ip, created_at__gte=timezone.now() - IP_WINDOW)
            .exclude(status=Order.Status.FAILED)
            .count()
        )
        if recent_from_ip >= IP_LIMIT:
            return "ip_limit"
    return None


@lru_cache(maxsize=1)
def _watermark_font() -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(Path(settings.BASE_DIR) / "static" / "fonts" / "VelaSans-Bold.otf"), 30)


def make_watermarked_preview(original: bytes) -> bytes:
    """Копия ≤512px по длинной стороне с диагональной сеткой «ShotForJob».
    Знак полупрозрачный белый с тёмной обводкой — читается и на светлом, и на
    тёмном фоне, а вырезать его из такого маленького кадра бессмысленно."""
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(original))).convert("RGBA")
    image.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE), Image.LANCZOS)

    font = _watermark_font()
    tile = Image.new("RGBA", (200, 96), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text(
        (100, 48), WATERMARK_TEXT, font=font, anchor="mm",
        fill=(255, 255, 255, 165), stroke_width=2, stroke_fill=(0, 0, 0, 95),
    )
    tile = tile.rotate(30, expand=True, resample=Image.BICUBIC)

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    for y in range(-tile.height, image.height + tile.height, tile.height - 20):
        offset = (y // (tile.height - 20)) % 2 * (tile.width // 2)
        for x in range(-tile.width + offset, image.width + tile.width, tile.width):
            layer.paste(tile, (x, y), tile)  # paste, а не alpha_composite: тот не принимает отрицательные x/y
    watermarked = Image.alpha_composite(image, layer).convert("RGB")

    buffer = io.BytesIO()
    watermarked.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


@transaction.atomic
def unlock(result: GeneratedResult, user) -> bool:
    """Открывает оригинал превью за 1 генерацию. Идемпотентно: уже открытый
    результат повторно не списывает. Возвращает True, если списание было.
    Бросает InsufficientBalanceError — тогда нужна оплата."""
    result = GeneratedResult.objects.select_for_update().select_related("order").get(pk=result.pk)
    if not result.is_locked:
        return False
    spend_generation(user, order=result.order)
    result.unlocked = True
    result.unlocked_at = timezone.now()
    result.save(update_fields=["unlocked", "unlocked_at"])
    return True
