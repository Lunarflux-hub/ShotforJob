"""
Отрисовка слайдов карусели в PNG 1080×1350 (формат 4:5 — максимальная
высота, которую Instagram показывает в ленте без обрезки).

Рисуем Pillow, а не headless-браузером: не тянем Chromium в Docker-образ,
а фирменный шрифт сайта (Vela Sans, static/fonts) Pillow читает напрямую.
Размер шрифта подбирается под длину текста (_fit_text), чтобы короткие
тексты были крупными, а длинные не вылезали за поля.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
PADDING = 96
CONTENT_WIDTH = WIDTH - 2 * PADDING

FONTS_DIR = Path(settings.BASE_DIR) / "static" / "fonts"


@dataclass(frozen=True)
class Theme:
    background: str
    text: str
    muted: str
    accent: str


THEMES = {
    "light": Theme(background="#FFFFFF", text="#0A0A0A", muted="#8A8A8A", accent="#0066FF"),
    "dark": Theme(background="#0B0B0F", text="#F5F5F5", muted="#8E8E93", accent="#5C9CFF"),
    "blue": Theme(background="#0066FF", text="#FFFFFF", muted="#BFD6FF", accent="#FFFFFF"),
}


@lru_cache(maxsize=64)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / f"VelaSans-{weight}.otf"), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Перенос по словам; слово длиннее строки режется посимвольно."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_width:
                line = candidate
                continue
            if line:
                lines.append(line)
            while draw.textlength(word, font=font) > max_width:
                cut = len(word)
                while cut > 1 and draw.textlength(word[:cut], font=font) > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    weight: str,
    max_size: int,
    min_size: int,
    max_height: int,
    line_spacing: float,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Самый крупный кегль из [min_size, max_size], при котором текст влезает
    в max_height. Возвращает (шрифт, строки, высота строки)."""
    size = max_size
    while True:
        font = _font(weight, size)
        lines = _wrap(draw, text, font, CONTENT_WIDTH)
        line_height = round(size * line_spacing)
        if len(lines) * line_height <= max_height or size <= min_size:
            return font, lines, line_height
        size -= 2


def _draw_lines(draw, lines, font, line_height, x, y, fill) -> int:
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _draw_footer(draw, theme: Theme, handle: str, index: int, total: int) -> None:
    font = _font("Medium", 30)
    y = HEIGHT - PADDING + 10
    if handle:
        draw.text((PADDING, y), handle, font=font, fill=theme.muted, anchor="ls")
    draw.text((WIDTH - PADDING, y), f"{index + 1}/{total}", font=font, fill=theme.muted, anchor="rs")


def _render_cover(draw, theme: Theme, slide: dict, total: int, handle: str) -> None:
    # Заголовок + подзаголовок, по вертикали — чуть выше центра
    title_font, title_lines, title_lh = _fit_text(draw, slide["title"], "ExtraBold", 112, 64, 620, 1.12)
    body_font, body_lines, body_lh = _fit_text(draw, slide["body"], "Regular", 46, 32, 260, 1.4)
    gap = 48
    block = len(title_lines) * title_lh + (gap + len(body_lines) * body_lh if slide["body"] else 0)
    y = max(PADDING + 80, (HEIGHT - block) // 2 - 60)

    draw.rounded_rectangle((PADDING, y - 70, PADDING + 96, y - 58), radius=6, fill=theme.accent)
    y = _draw_lines(draw, title_lines, title_font, title_lh, PADDING, y, theme.text)
    if slide["body"]:
        _draw_lines(draw, body_lines, body_font, body_lh, PADDING, y + gap, theme.muted)

    swipe_font = _font("SemiBold", 36)
    draw.text((PADDING, HEIGHT - PADDING - 70), "Листайте →", font=swipe_font, fill=theme.accent, anchor="ls")
    _draw_footer(draw, theme, handle, 0, total)


def _render_content(draw, theme: Theme, slide: dict, index: int, total: int, handle: str) -> None:
    is_last = index == total - 1
    y = PADDING + 20
    if not is_last:
        number_font = _font("ExtraBold", 120)
        draw.text((PADDING - 6, y), f"{index:02d}", font=number_font, fill=theme.accent)
        y += 190
    else:
        draw.rounded_rectangle((PADDING, y + 40, PADDING + 96, y + 52), radius=6, fill=theme.accent)
        y += 110

    title_font, title_lines, title_lh = _fit_text(draw, slide["title"], "Bold", 76, 48, 330, 1.18)
    y = _draw_lines(draw, title_lines, title_font, title_lh, PADDING, y, theme.text)

    if slide["body"]:
        y += 44
        available = HEIGHT - PADDING - 90 - y
        body_font, body_lines, body_lh = _fit_text(draw, slide["body"], "Regular", 46, 30, available, 1.45)
        _draw_lines(draw, body_lines, body_font, body_lh, PADDING, y, theme.text)

    _draw_footer(draw, theme, handle, index, total)


def render_slide(slide: dict, index: int, total: int, theme_name: str, handle: str = "") -> bytes:
    theme = THEMES.get(theme_name, THEMES["light"])
    image = Image.new("RGB", (WIDTH, HEIGHT), theme.background)
    draw = ImageDraw.Draw(image)

    if index == 0:
        _render_cover(draw, theme, slide, total, handle)
    else:
        _render_content(draw, theme, slide, index, total, handle)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def render_carousel(slides: list[dict], theme_name: str, handle: str = "") -> list[bytes]:
    return [render_slide(slide, i, len(slides), theme_name, handle) for i, slide in enumerate(slides)]
