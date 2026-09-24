"""
Тексты слайдов карусели. Нейросеть вызывается через OpenAI-совместимый
эндпоинт Polza.ai (/chat/completions) — тот же аккаунт и ключ, что и для
генерации фото (POLZA_API_KEY), но другой хост (POLZA_CHAT_BASE_URL).

Слайд: {"layout", "emoji", "title", "body", "items", "value"} — нейросеть
сама выбирает макет каждого слайда (см. renderer.LAYOUTS), чтобы карусель
не была однообразной.
"""
from __future__ import annotations

import json
import logging
import re

from django.conf import settings
from openai import OpenAI, OpenAIError

from .renderer import LAYOUTS, first_emoji

logger = logging.getLogger(__name__)

# Лимиты длины под вёрстку слайда (services/renderer.py): длиннее — текст
# начинает мельчить, а это на телефоне уже не читается.
TITLE_MAX = {"cover": 70, "cta": 60, "stat": 70, "quote": 60}
TITLE_MAX_DEFAULT = 60
BODY_MAX = {"cover": 110, "quote": 200, "stat": 160, "cta": 140}
BODY_MAX_DEFAULT = 280
ITEM_MAX = 80
ITEMS_MAX = 5
VALUE_MAX = 18
CAPTION_MAX = 2000

SYSTEM_PROMPT = f"""Ты — SMM-копирайтер. Пишешь тексты для карусели в Instagram на русском языке.
Верни СТРОГО JSON без пояснений и без markdown:
{{"slides": [{{"layout": "...", "emoji": "...", "title": "...", "body": "...", "items": [], "value": ""}}, ...], "caption": "..."}}

Макеты (layout) и какие поля в них заполнять:
- "cover" — обложка, только первый слайд. title — цепляющий заголовок до {TITLE_MAX["cover"]} символов, body — подзаголовок до {BODY_MAX["cover"]} символов с обещанием пользы.
- "text" — одна мысль: title до {TITLE_MAX_DEFAULT} символов, body до {BODY_MAX_DEFAULT} символов.
- "list" — список: title до {TITLE_MAX_DEFAULT} символов, items — 3–{ITEMS_MAX} коротких пунктов до {ITEM_MAX} символов, каждый пункт начинается с подходящего эмодзи.
- "stat" — яркая цифра: value — сама цифра коротко («7 сек», «×3», «80%»), title — что она значит, body — пояснение до {BODY_MAX["stat"]} символов. Только правдоподобные общеизвестные цифры, не выдумывай исследования.
- "quote" — цитата или мысль-правило: body — текст цитаты до {BODY_MAX["quote"]} символов, title — автор или источник (если цитата не чья-то, напиши «Правило» или «Совет»).
- "cta" — только последний слайд: вывод и призыв. title, body до {BODY_MAX["cta"]} символов, value — текст кнопки до {VALUE_MAX} символов («Сохранить 🔖», «Написать в директ»).

Правила:
- Ровно столько слайдов, сколько попросят. Первый — cover, последний — cta.
- Средние слайды делай разнообразными: используй минимум два разных макета из text / list / stat / quote, не ставь подряд три одинаковых.
- emoji — ровно один подходящий по смыслу эмодзи на каждый слайд.
- В title и body можно максимум один эмодзи, и только если он к месту. Без хэштегов, markdown и нумерации в заголовках — номера дорисуются автоматически.
- Конкретика, примеры, живой язык на «вы», без канцелярита и воды.
- caption — подпись к посту: 2–4 коротких абзаца, 1–3 уместных эмодзи, в конце 5–8 релевантных хэштегов на русском."""


class CopywriterError(Exception):
    pass


_MARKDOWN = re.compile(r"[*_#`]+")


def clean_text(text, limit: int) -> str:
    text = _MARKDOWN.sub("", str(text or ""))
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip(" ,.;:—-") + "…"
    return text


def normalize_slide(raw: dict, *, fallback_layout: str = "text") -> dict:
    """Приводит один слайд к полному виду с обрезкой под лимиты вёрстки.
    Используется и для ответа нейросети, и для правок пользователя."""
    layout = raw.get("layout") if raw.get("layout") in LAYOUTS else fallback_layout
    items = raw.get("items") if isinstance(raw.get("items"), list) else []
    return {
        "layout": layout,
        "emoji": first_emoji(str(raw.get("emoji") or "")),
        "title": clean_text(raw.get("title"), TITLE_MAX.get(layout, TITLE_MAX_DEFAULT)),
        "body": clean_text(raw.get("body"), BODY_MAX.get(layout, BODY_MAX_DEFAULT)),
        "items": [clean_text(item, ITEM_MAX) for item in items if str(item or "").strip()][:ITEMS_MAX],
        "value": clean_text(raw.get("value"), VALUE_MAX),
    }


def normalize_slides(raw_slides: list, count: int | None = None, *, enforce_structure: bool = False) -> list[dict]:
    """enforce_structure=True — для ответа нейросети: первый слайд обложка,
    последний призыв. Правки пользователя так не форсируются — в редакторе
    макет любого блока можно поменять."""
    raw_slides = [s for s in raw_slides if isinstance(s, dict)]
    if count is not None and len(raw_slides) > count:
        # Лишние слайды выкидываем из середины: последний — призыв, его терять нельзя
        raw_slides = raw_slides[: count - 1] + raw_slides[-1:]

    slides = []
    for i, raw in enumerate(raw_slides):
        fallback = "cover" if i == 0 else "list" if raw.get("items") else "text"
        slide = normalize_slide(raw, fallback_layout=fallback)
        if enforce_structure:
            if i == 0:
                slide["layout"] = "cover"
            elif i == len(raw_slides) - 1:
                slide["layout"] = "cta"
            elif slide["layout"] in ("cover", "cta"):
                slide["layout"] = "list" if slide["items"] else "text"
        slides.append(slide)
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
    # «5 шагов» тратит последний слайд на пятый шаг вместо призыва к действию.
    user_prompt = (
        f"Тема карусели: {topic}\n"
        f"Количество слайдов: {slides_count}\n"
        f"Структура: слайд 1 — cover; слайды 2–{slides_count - 1} — по одной мысли "
        f"(всего {slides_count - 2}), разные макеты; слайд {slides_count} — cta, "
        f"а не очередной пункт."
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
    slides = normalize_slides(data.get("slides") or [], slides_count, enforce_structure=True)
    if len(slides) < 2:
        logger.warning("Мало слайдов в ответе нейросети: %s", content[:500])
        raise CopywriterError("Нейросеть вернула слишком мало слайдов, попробуйте ещё раз")

    # В подписи эмодзи уместны без ограничений: она публикуется текстом
    caption = str(data.get("caption") or "").strip()[:CAPTION_MAX]
    return slides, caption
