"""
Тексты слайдов карусели. Нейросеть вызывается через OpenAI-совместимый
эндпоинт Polza.ai (/chat/completions) — тот же аккаунт и ключ, что и для
генерации фото (POLZA_API_KEY), но другой хост (POLZA_CHAT_BASE_URL).
"""
from __future__ import annotations

import json
import logging
import re

from django.conf import settings
from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

# Лимиты длины под вёрстку слайда 1080×1350 (services/renderer.py): длиннее —
# текст начинает мельчить, а это на телефоне уже не читается.
COVER_TITLE_MAX = 70
COVER_BODY_MAX = 110
TITLE_MAX = 60
BODY_MAX = 280
CAPTION_MAX = 2000

SYSTEM_PROMPT = f"""Ты — SMM-копирайтер. Пишешь тексты для карусели в Instagram на русском языке.
Верни СТРОГО JSON без пояснений и без markdown:
{{"slides": [{{"title": "...", "body": "..."}}, ...], "caption": "..."}}

Правила:
- Ровно столько слайдов, сколько попросят.
- Слайд 1 — обложка: цепляющий заголовок до {COVER_TITLE_MAX} символов и подзаголовок до {COVER_BODY_MAX} символов, который обещает пользу.
- Средние слайды — по одной мысли на слайд: заголовок до {TITLE_MAX} символов, текст до {BODY_MAX} символов. Конкретика, примеры, цифры, без воды.
- Последний слайд — вывод и призыв к действию (сохранить пост, подписаться, написать в комментариях).
- В слайдах никаких эмодзи, хэштегов, markdown-разметки и нумерации в заголовках — номер слайда дорисуется автоматически.
- caption — подпись к посту: 2–4 коротких абзаца, можно 1–3 уместных эмодзи, в конце 5–8 релевантных хэштегов на русском.
- Пиши живо, на «вы», без канцелярита."""


class CopywriterError(Exception):
    pass


# Эмодзи и прочие символы вне шрифта Vela Sans — на слайде они стали бы «тофу»-квадратами
_UNSUPPORTED_CHARS = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U00002B00-\U00002BFF]"
)
_MARKDOWN = re.compile(r"[*_#`]+")


def clean_text(text: str, limit: int) -> str:
    text = _UNSUPPORTED_CHARS.sub("", str(text or ""))
    text = _MARKDOWN.sub("", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip(" ,.;:—-") + "…"
    return text


def normalize_slides(raw_slides: list, count: int | None = None) -> list[dict]:
    """Приводит слайды к [{"title", "body"}] с обрезкой под лимиты вёрстки.
    Используется и для ответа нейросети, и для правок пользователя."""
    slides = []
    for i, slide in enumerate(raw_slides):
        if not isinstance(slide, dict):
            continue
        is_cover = i == 0
        slides.append(
            {
                "title": clean_text(slide.get("title"), COVER_TITLE_MAX if is_cover else TITLE_MAX),
                "body": clean_text(slide.get("body"), COVER_BODY_MAX if is_cover else BODY_MAX),
            }
        )
    if count is not None:
        slides = slides[:count]
    return slides


def _extract_json(content: str) -> dict:
    # Модели иногда оборачивают ответ в ```json … ``` — берём от первой { до последней }
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise CopywriterError("Нейросеть вернула ответ не в формате JSON")
    try:
        return json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise CopywriterError("Не удалось разобрать ответ нейросети") from exc


def write_carousel(topic: str, slides_count: int) -> tuple[list[dict], str]:
    """Возвращает (slides, caption)."""
    client = OpenAI(api_key=settings.POLZA_API_KEY, base_url=settings.POLZA_CHAT_BASE_URL, timeout=120)
    # Структуру проговариваем явно с номерами: иначе модель на теме вида
    # «5 шагов» тратит последний слайд на пятый шаг вместо призыва к действию,
    # а renderer рисует последний слайд как финальный (без номера).
    user_prompt = (
        f"Тема карусели: {topic}\n"
        f"Количество слайдов: {slides_count}\n"
        f"Структура: слайд 1 — обложка; слайды 2–{slides_count - 1} — по одной мысли "
        f"(всего {slides_count - 2}); слайд {slides_count} — вывод и призыв к действию, "
        f"не очередной пункт."
    )
    try:
        response = client.chat.completions.create(
            model=settings.POLZA_TEXT_MODEL,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
    except OpenAIError as exc:
        logger.exception("Polza.ai chat error")
        raise CopywriterError("Сервис генерации текста недоступен, попробуйте позже") from exc

    content = response.choices[0].message.content or ""
    data = _extract_json(content)
    slides = normalize_slides(data.get("slides") or [], slides_count)
    if len(slides) < 2:
        logger.warning("Мало слайдов в ответе нейросети: %s", content[:500])
        raise CopywriterError("Нейросеть вернула слишком мало слайдов, попробуйте ещё раз")

    # В подписи эмодзи уместны: она публикуется текстом, а не рисуется шрифтом
    caption = str(data.get("caption") or "").strip()[:CAPTION_MAX]
    return slides, caption
