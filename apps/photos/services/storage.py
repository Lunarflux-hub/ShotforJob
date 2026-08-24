"""
Загрузка результатов генерации в Yandex Cloud Object Storage.
Хранилище S3-совместимое, поэтому используем boto3 с кастомным endpoint_url.

ОБНОВЛЕНО: раньше объекты грузились с ACL="public-read", но это упирается в
настройки публичного доступа самого бакета в Yandex Cloud (если публичный
доступ на бакете не включён — объект остаётся недоступен даже с этим ACL,
отсюда AccessDenied). Более надёжный и не зависящий от настроек бакета
способ — держать бакет полностью приватным и отдавать пользователю
presigned URL (временную подписанную ссылку на скачивание).
"""
from __future__ import annotations

import logging
import uuid

import boto3
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Срок жизни ссылки на скачивание. Берём с запасом, но она всё равно
# генерируется заново при каждом обращении к API (см. serializers.py),
# так что реальный срок хранения файла определяется только бакетом.
PRESIGNED_URL_EXPIRES_IN = 60 * 60 * 24 * 7  # 7 дней


def _get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.YC_S3_ENDPOINT_URL,
        aws_access_key_id=settings.YC_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.YC_S3_SECRET_ACCESS_KEY,
        region_name=settings.YC_S3_REGION,
    )


def upload_bytes(data: bytes, key: str, content_type: str = "image/png") -> None:
    """Загружает байты в приватный бакет (без ACL — публичный доступ не нужен)."""
    client = _get_s3_client()
    client.put_object(
        Bucket=settings.YC_S3_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def download_bytes(key: str) -> bytes:
    """
    Скачивает объект из приватного бакета по ключу — используется, чтобы
    вшить фото как inline-вложение в письмо поддержки
    (см. apps/support/tasks.py).
    """
    client = _get_s3_client()
    obj = client.get_object(Bucket=settings.YC_S3_BUCKET_NAME, Key=key)
    return obj["Body"].read()


def generate_presigned_url(key: str, expires_in: int = PRESIGNED_URL_EXPIRES_IN) -> str:
    """
    Генерирует временную подписанную ссылку на объект в приватном бакете.
    Вызывается заново при каждой сериализации GeneratedResult (см.
    apps/photos/serializers.py), поэтому не протухает для пользователя,
    даже если он откроет историю заказов спустя долгое время.
    """
    client = _get_s3_client()
    try:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.YC_S3_BUCKET_NAME, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception:
        logger.exception("Не удалось сгенерировать presigned URL для ключа %s", key)
        raise


def upload_from_url(source_url: str, order_id: str) -> tuple[str, str]:
    """
    Скачивает сгенерированное изображение по URL, отданному Polza.ai,
    и загружает его в Yandex Object Storage.
    Возвращает (s3_key, presigned_url).
    """
    resp = requests.get(source_url, timeout=60)
    resp.raise_for_status()

    key = f"results/{order_id}/{uuid.uuid4()}.png"
    upload_bytes(resp.content, key, content_type="image/png")
    return key, generate_presigned_url(key)


def upload_generated_bytes(data: bytes, order_id: str) -> tuple[str, str]:
    """
    Загружает уже готовые байты изображения (например, если Polza.ai вернул
    результат как base64 вместо URL) в Yandex Object Storage.
    Возвращает (s3_key, presigned_url).
    """
    key = f"results/{order_id}/{uuid.uuid4()}.png"
    upload_bytes(data, key, content_type="image/png")
    return key, generate_presigned_url(key)