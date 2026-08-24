"""
Клиент для Polza.ai Media API.

ОБНОВЛЕНО: Polza.ai для генерации медиа (изображения/видео/аудио) использует
не OpenAI SDK, а собственный эндпоинт POST /v1/media, который принимает
запрос и сразу отдаёт объект со статусом "pending" — результат нужно
забирать отдельным поллингом GET /v1/media/{id}.

Официальная схема (https://polza.ai/docs/api-reference/media/create):

POST https://polza.ai/api/v1/media
{
  "model": "google/gemini-3.1-flash-lite-image",
  "input": {
    "prompt": "...",
    "images": [{"type": "url"|"base64", "data": "..."}],
    "aspect_ratio": "1:1",
    "image_resolution": "1K"
  }
}
-> {"id": "gen_...", "status": "pending", ...}

GET https://polza.ai/api/v1/media/{id}
-> {"id": "gen_...", "status": "completed"|"failed"|..., "data": {...}}

Точная форма поля `data` при status="completed" в открытой документации не
приведена (плейсхолдер вместо примера), поэтому ниже стоит защитный парсинг
нескольких вероятных вариантов + логирование сырого ответа на уровне DEBUG.
Если после первого реального запроса форма окажется другой — пришлите мне
залогированный JSON, поправлю _extract_result под неё.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import time
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

MEDIA_ENDPOINT = "/api/v1/media"
DEFAULT_POLL_INTERVAL_SEC = 3
DEFAULT_POLL_TIMEOUT_SEC = 180  # держим с запасом под CELERY_TASK_TIME_LIMIT (5 мин)

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class PolzaClientError(Exception):
    pass


@dataclass
class GenerationResult:
    image_url: str | None = None
    image_bytes: bytes | None = None


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.POLZA_API_KEY}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return settings.POLZA_BASE_URL.rstrip("/")


IDENTITY_PRESERVATION_INSTRUCTION = (
    "Keep the exact facial identity of the person from the reference photo(s) "
    "completely unchanged: same face shape, eye shape and color, nose, mouth, "
    "eyebrows, skin tone, and any distinguishing features. This must be "
    "immediately recognizable as the same specific person, not a similar-looking "
    "one. Only change what is explicitly described below (background, clothing, "
    "lighting, framing, artistic style) — never alter the facial structure itself."
)


def _image_to_data_url(path: str) -> dict:
    """Кодирует локальный файл в base64 для поля images[].data."""
    mime_type, _ = mimetypes.guess_type(path)
    mime_type = mime_type or "image/jpeg"
    with open(path, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")
    return {"type": "base64", "data": f"data:{mime_type};base64,{b64_data}"}


def _create_media_generation(prompt: str, reference_image_paths: list[str] | None = None) -> dict:
    payload = {
        "model": settings.POLZA_IMAGE_MODEL,
        "input": {
            "prompt": prompt,
            "aspect_ratio": "1:1",
            "image_resolution": "1K",
        },
    }
    if reference_image_paths:
        # При image-to-image явно просим модель не менять черты лица —
        # без этого модели (в т.ч. Nano Banana) склонны "додумывать" лицо
        # заново, особенно при сильной стилизации.
        payload["input"]["prompt"] = f"{IDENTITY_PRESERVATION_INSTRUCTION}\n\n{prompt}"
        payload["input"]["images"] = [_image_to_data_url(p) for p in reference_image_paths]
        # strength — сила трансформации (0-1). Чем ниже, тем ближе результат
        # к референсному фото (меньше искажений лица), чем выше — тем больше
        # свободы у модели менять сцену, но и риск "уплыть" от оригинала.
        # Подбирайте под свои стили: для строгих документных фото уместно
        # 0.3-0.4, для креативных — можно поднять до 0.6-0.7.
        payload["input"]["strength"] = settings.POLZA_IMG2IMG_STRENGTH

    try:
        resp = requests.post(
            f"{_base_url()}{MEDIA_ENDPOINT}", headers=_headers(), json=payload, timeout=120
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Polza.ai POST /media error")
        raise PolzaClientError(f"Ошибка запроса к Polza.ai: {exc}") from exc

    data = resp.json()
    logger.debug("Polza.ai POST /media response: %s", data)
    return data


def _poll_media_status(media_id: str) -> dict:
    deadline = time.monotonic() + DEFAULT_POLL_TIMEOUT_SEC

    while time.monotonic() < deadline:
        try:
            resp = requests.get(
                f"{_base_url()}{MEDIA_ENDPOINT}/{media_id}", headers=_headers(), timeout=120
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Polza.ai GET /media/%s error", media_id)
            raise PolzaClientError(f"Ошибка опроса статуса Polza.ai: {exc}") from exc

        data = resp.json()
        logger.debug("Polza.ai GET /media/%s response: %s", media_id, data)

        status = data.get("status")
        if status in TERMINAL_STATUSES:
            return data

        time.sleep(DEFAULT_POLL_INTERVAL_SEC)

    raise PolzaClientError(f"Превышен таймаут ожидания результата Polza.ai (id={media_id})")


def _extract_result(status_payload: dict) -> GenerationResult:
    if status_payload.get("status") == "failed":
        error = status_payload.get("error") or {}
        message = error.get("message", "Неизвестная ошибка генерации")
        raise PolzaClientError(f"Polza.ai: {message}")

    if status_payload.get("status") == "cancelled":
        raise PolzaClientError("Генерация была отменена Polza.ai")

    data = status_payload.get("data")
    if not data:
        raise PolzaClientError(
            "Polza.ai вернул статус completed без поля data — проверьте сырой ответ в логах"
        )

    # Защитный парсинг разных вероятных форм поля `data`.
    if isinstance(data, str):
        if data.startswith("http"):
            return GenerationResult(image_url=data)
        return GenerationResult(image_bytes=base64.b64decode(data))

    if isinstance(data, dict):
        if data.get("url"):
            return GenerationResult(image_url=data["url"])
        if data.get("b64_json"):
            return GenerationResult(image_bytes=base64.b64decode(data["b64_json"]))
        images = data.get("images") or data.get("data")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, str):
                return GenerationResult(image_url=first)
            if isinstance(first, dict):
                if first.get("url"):
                    return GenerationResult(image_url=first["url"])
                if first.get("b64_json"):
                    return GenerationResult(image_bytes=base64.b64decode(first["b64_json"]))

    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, str):
            return GenerationResult(image_url=first)
        if isinstance(first, dict) and first.get("url"):
            return GenerationResult(image_url=first["url"])

    raise PolzaClientError(
        f"Не удалось распознать формат результата Polza.ai, сырые данные: {data!r}"
    )


def generate_image_from_reference(
    prompt: str, reference_image_paths: list[str], size: str = "1024x1024"
) -> GenerationResult:
    """Image-to-image: создаёт задачу и дожидается результата (поллинг)."""
    created = _create_media_generation(prompt, reference_image_paths)

    if created.get("status") in TERMINAL_STATUSES:
        final = created
    else:
        media_id = created.get("id")
        if not media_id:
            raise PolzaClientError(f"Polza.ai не вернул id генерации: {created!r}")
        final = _poll_media_status(media_id)

    return _extract_result(final)


def generate_image_from_prompt(prompt: str, size: str = "1024x1024") -> GenerationResult:
    """Генерация "с нуля" по тексту, без референсных фото."""
    return generate_image_from_reference(prompt, reference_image_paths=[], size=size)