"""
Сборка финального промпта для Polza.ai из:
  1) prompt_template выбранного PhotoStyle,
  2) параметров, которые пользователь настроил на /workstation:
     - одежда (clothing)
     - фон/окружение (background_type + background_color / background_image)

PhotoStyle.prompt_template остаётся "базой" (общий стиль/качество/освещение),
а сюда добавляются конкретные детали, которые раньше терялись.
"""
from __future__ import annotations

from .. import models

CLOTHING_PROMPTS: dict[str, str] = {
    "casual": "wearing casual everyday clothing (e.g. a simple t-shirt or sweater), relaxed style",
    "formal": "wearing formal business attire, suit jacket, polished professional look",
    "sport": "wearing sportswear / athletic clothing",
    # Одежда для документных стилей
    "jacket": "wearing a formal jacket / business blazer over a shirt",
    "shirt": "wearing a plain collared shirt, no jacket",
}

BACKGROUND_PROMPTS: dict[str, str] = {
    "office": "modern blurred office interior background, soft bokeh, professional workspace",
    "nature": "natural outdoor background, greenery and soft daylight, shallow depth of field",
}

BACKGROUND_IMAGE_INSTRUCTION = (
    "Place the person in front of the background shown in the separate background "
    "reference image provided below. Blend lighting and perspective naturally so the "
    "person looks like they were actually photographed in that scene. Do not copy any "
    "person or face from the background reference — use it only for the background scene."
)


def _solid_color_prompt(hex_color: str) -> str:
    return (
        f"plain solid-color studio background, exact color {hex_color}, "
        "no texture, no objects, evenly lit backdrop"
    )


def build_prompt(order: "models.Order") -> str:
    """Собирает итоговый текстовый промпт для заказа с учётом настроек пользователя."""
    parts = [order.style.prompt_template.strip()]

    if order.clothing:
        clothing_phrase = CLOTHING_PROMPTS.get(order.clothing)
        if clothing_phrase:
            parts.append(clothing_phrase)

    if order.background_image:
        parts.append(BACKGROUND_IMAGE_INSTRUCTION)
    elif order.background_type == "solid" and order.background_color:
        parts.append(_solid_color_prompt(order.background_color))
    elif order.background_type in BACKGROUND_PROMPTS:
        parts.append(BACKGROUND_PROMPTS[order.background_type])
    elif not order.background_type and order.background_color:
        # Документные стили: отдельного выбора локации нет, только цвет фона.
        parts.append(_solid_color_prompt(order.background_color))

    return ", ".join(parts)
