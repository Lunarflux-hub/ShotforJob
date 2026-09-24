"""
Отрисовка слайдов карусели в PNG (1080×1350 — формат 4:5, максимальная
высота без обрезки в ленте Instagram; или квадрат 1080×1080).

Рисуем Pillow, а не headless-браузером: не тянем Chromium в Docker-образ,
а фирменный шрифт сайта (Vela Sans, static/fonts) Pillow читает напрямую.
Цветные эмодзи — из Noto Color Emoji (пакет fonts-noto-color-emoji в
Dockerfile): это растровый шрифт с одним размером 109px, поэтому эмодзи
рисуются отдельной картинкой и масштабируются (_emoji_image).

Слайд: {"layout", "emoji", "title", "body", "items", "value"} — какие поля
нужны каждому макету, см. LAYOUTS и _render_* ниже. Оформление всей
карусели — тема (THEMES) + настройки design (DEFAULT_DESIGN).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageColor, ImageDraw, ImageFont

WIDTH = 1080
HEIGHTS = {"portrait": 1350, "square": 1080}
PADDING = 96
FOOTER_SPACE = 90

FONTS_DIR = Path(settings.BASE_DIR) / "static" / "fonts"
EMOJI_BITMAP_SIZE = 109  # единственный размер, который есть в Noto Color Emoji (CBDT)

LAYOUTS = ("cover", "text", "list", "stat", "quote", "cta")


# ---------------------------------------------------------------- темы ----

@dataclass(frozen=True)
class Theme:
    label: str
    background: str | tuple[str, str]  # цвет или (начало, конец) диагонального градиента
    text: str
    muted: str
    accent: str
    surface: str  # подложка пунктов списка и т.п.; поддерживает альфу (#RRGGBBAA)
    on_accent: str  # текст на акцентной кнопке


THEMES = {
    "light": Theme("Светлая", "#FFFFFF", "#0A0A0A", "#8A8A8A", "#0066FF", "#F2F4F8", "#FFFFFF"),
    "dark": Theme("Тёмная", "#0B0B0F", "#F5F5F5", "#8E8E93", "#5C9CFF", "#1C1C22", "#0B0B0F"),
    "blue": Theme("Синяя", "#0066FF", "#FFFFFF", "#BFD6FF", "#FFFFFF", "#FFFFFF26", "#0066FF"),
    "cream": Theme("Крем", "#F6F0E6", "#2B2420", "#8C7F72", "#C8553D", "#EADFCC", "#FFFFFF"),
    "mint": Theme("Мята", "#E6F6EF", "#0F2F24", "#5C7F71", "#10A37F", "#CDEDDF", "#FFFFFF"),
    "lavender": Theme("Лаванда", "#EEEAFE", "#231A4A", "#7B72A8", "#6D4AFF", "#DDD5FD", "#FFFFFF"),
    "peach": Theme("Персик", "#FFE9DF", "#3A1F14", "#9C6F5E", "#FF6B3D", "#FFD6C4", "#FFFFFF"),
    "forest": Theme("Лес", "#12261E", "#F0F5EF", "#9DB3A6", "#C6F16D", "#1F3D30", "#12261E"),
    "neon": Theme("Неон", "#0A0A0A", "#FFFFFF", "#8A8A8A", "#D4FF3A", "#1C1C1C", "#0A0A0A"),
    "sunset": Theme("Закат", ("#FF7E5F", "#6A3093"), "#FFFFFF", "#FFE0D3", "#FFFFFF", "#FFFFFF2E", "#6A3093"),
    "ocean": Theme("Океан", ("#0F2027", "#2C5364"), "#FFFFFF", "#A9C6D3", "#6DD5ED", "#FFFFFF1A", "#0F2027"),
    "candy": Theme("Карамель", ("#FFD1DC", "#FAD0C4"), "#3B1C2A", "#8E5B6E", "#D6336C", "#FFFFFF80", "#FFFFFF"),
}

DEFAULT_DESIGN = {
    "accent": "",          # свой акцентный цвет (#RRGGBB), пусто — из темы
    "align": "left",       # left | center
    "pattern": "none",     # none | dots | grid | circles | frame
    "aspect": "portrait",  # portrait (4:5) | square (1:1)
    "title_scale": "m",    # s | m | l
    "show_numbers": True,  # крупные номера на слайдах-пунктах
    "show_counter": True,  # «2/7» в углу
    "show_swipe": True,    # «Листайте →» на обложке
}
PATTERNS = ("none", "dots", "grid", "circles", "frame")
TITLE_SCALES = {"s": 0.85, "m": 1.0, "l": 1.15}
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_design(design: dict | None) -> dict:
    """Дополняет design значениями по умолчанию и выкидывает мусор."""
    result = dict(DEFAULT_DESIGN)
    design = design or {}
    if HEX_COLOR.match(str(design.get("accent") or "")):
        result["accent"] = design["accent"]
    if design.get("align") in ("left", "center"):
        result["align"] = design["align"]
    if design.get("pattern") in PATTERNS:
        result["pattern"] = design["pattern"]
    if design.get("aspect") in HEIGHTS:
        result["aspect"] = design["aspect"]
    if design.get("title_scale") in TITLE_SCALES:
        result["title_scale"] = design["title_scale"]
    for flag in ("show_numbers", "show_counter", "show_swipe"):
        if isinstance(design.get(flag), bool):
            result[flag] = design[flag]
    return result


# ------------------------------------------------------ шрифты и эмодзи ----

@lru_cache(maxsize=128)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / f"VelaSans-{weight}.otf"), size)


@lru_cache(maxsize=1)
def _emoji_font() -> ImageFont.FreeTypeFont | None:
    path = getattr(settings, "EMOJI_FONT_PATH", "")
    if not path or not Path(path).exists():
        return None
    return ImageFont.truetype(path, EMOJI_BITMAP_SIZE)


# Последовательность эмодзи: флаг из двух regional indicators или символ из
# эмодзи-диапазонов (+ вариационный селектор, тон кожи, ZWJ-склейки).
# Стрелки (U+2190–21FF) сюда не входят — они есть в Vela Sans и рисуются текстом.
EMOJI_SEQUENCE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿]"
    "️?[\U0001F3FB-\U0001F3FF]?"
    "(?:‍[\U0001F000-\U0001FAFF☀-➿]️?[\U0001F3FB-\U0001F3FF]?)*)"
)


@lru_cache(maxsize=512)
def _emoji_image(sequence: str, size: int) -> Image.Image | None:
    """Эмодзи как RGBA-картинка size×size, или None, если такого глифа нет
    (или нет самого шрифта) — тогда символ просто пропускается."""
    font = _emoji_font()
    if font is None:
        return None
    canvas = Image.new("RGBA", (EMOJI_BITMAP_SIZE * 2, EMOJI_BITMAP_SIZE * 2), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((0, 0), sequence, font=font, embedded_color=True)
    bbox = canvas.getbbox()
    if bbox is None:
        return None
    glyph = canvas.crop(bbox)
    glyph.thumbnail((size, size), Image.LANCZOS)
    return glyph


def first_emoji(text: str) -> str:
    match = EMOJI_SEQUENCE.search(text or "")
    return match.group(0) if match else ""


def _segments(text: str) -> list[tuple[bool, str]]:
    """Режет строку на куски [(это_эмодзи, текст), ...]."""
    parts, pos = [], 0
    for match in EMOJI_SEQUENCE.finditer(text):
        if match.start() > pos:
            parts.append((False, text[pos : match.start()]))
        parts.append((True, match.group(0)))
        pos = match.end()
    if pos < len(text):
        parts.append((False, text[pos:]))
    return parts


# ------------------------------------------------------------- холст ------

class Canvas:
    def __init__(self, theme: Theme, design: dict):
        self.theme = theme
        self.design = design
        self.accent = design["accent"] or theme.accent
        self.w, self.h = WIDTH, HEIGHTS[design["aspect"]]
        self.content_w = self.w - 2 * PADDING
        self.center = design["align"] == "center"
        self.scale = TITLE_SCALES[design["title_scale"]]
        self.image = Image.new("RGBA", (self.w, self.h))
        self._paint_background()
        self.draw = ImageDraw.Draw(self.image)
        self._paint_pattern()

    # --- фон ---
    def _paint_background(self):
        bg = self.theme.background
        if isinstance(bg, tuple):
            start = Image.new("RGBA", (self.w, self.h), ImageColor.getrgb(bg[0]))
            end = Image.new("RGBA", (self.w, self.h), ImageColor.getrgb(bg[1]))
            # диагональная маска: вертикальный градиент, повёрнутый на 45°
            mask = Image.linear_gradient("L").rotate(45, expand=True)
            side = mask.width // 2
            mask = mask.crop((side // 2, side // 2, side // 2 + side, side // 2 + side))
            self.image = Image.composite(end, start, mask.resize((self.w, self.h)))
        else:
            self.image.paste(ImageColor.getrgb(bg), (0, 0, self.w, self.h))

    def _overlay(self, painter) -> None:
        """Рисует полупрозрачные элементы на отдельном слое и накладывает его."""
        layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        painter(ImageDraw.Draw(layer))
        self.image.alpha_composite(layer)

    def _rgba(self, color: str, alpha: int | None = None) -> tuple:
        rgba = ImageColor.getrgb(color)
        rgba = rgba if len(rgba) == 4 else (*rgba, 255)
        return (*rgba[:3], alpha) if alpha is not None else rgba

    def _paint_pattern(self):
        pattern = self.design["pattern"]
        muted = self.theme.muted
        if pattern == "dots":
            self._overlay(lambda d: [
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=self._rgba(muted, 70))
                for x in range(54, self.w, 54) for y in range(54, self.h, 54)
            ])
        elif pattern == "grid":
            def grid(d):
                for x in range(0, self.w, 90):
                    d.line((x, 0, x, self.h), fill=self._rgba(muted, 40), width=2)
                for y in range(0, self.h, 90):
                    d.line((0, y, self.w, y), fill=self._rgba(muted, 40), width=2)
            self._overlay(grid)
        elif pattern == "circles":
            def circles(d):
                d.ellipse((self.w - 320, -260, self.w + 320, 380), fill=self._rgba(self.accent, 40))
                d.ellipse((-300, self.h - 300, 260, self.h + 260), fill=self._rgba(self.accent, 28))
            self._overlay(circles)
        elif pattern == "frame":
            self._overlay(lambda d: d.rounded_rectangle(
                (36, 36, self.w - 36, self.h - 36), radius=36, outline=self._rgba(self.accent, 150), width=4
            ))

    def surface_box(self, box, radius=28):
        self._overlay(lambda d: d.rounded_rectangle(box, radius=radius, fill=self._rgba(self.theme.surface)))

    # --- текст с эмодзи ---
    def measure(self, text: str, font) -> float:
        width = 0.0
        for is_emoji, part in _segments(text):
            if is_emoji:
                width += font.size * 1.05 if _emoji_image(part, font.size) else 0
            else:
                width += self.draw.textlength(part, font=font)
        return width

    def draw_run(self, x: float, y: float, text: str, font, fill) -> None:
        for is_emoji, part in _segments(text):
            if is_emoji:
                glyph = _emoji_image(part, font.size)
                if glyph:
                    self.image.alpha_composite(glyph, (round(x), round(y + font.size * 0.12)))
                    x += font.size * 1.05
            else:
                self.draw.text((x, y), part, font=font, fill=fill)
                x += self.draw.textlength(part, font=font)

    def wrap(self, text: str, font, max_width: int) -> list[str]:
        """Перенос по словам; слово длиннее строки режется посимвольно."""
        lines: list[str] = []
        for paragraph in (text or "").split("\n"):
            line = ""
            for word in paragraph.split():
                candidate = f"{line} {word}".strip()
                if self.measure(candidate, font) <= max_width:
                    line = candidate
                    continue
                if line:
                    lines.append(line)
                while self.measure(word, font) > max_width and len(word) > 1:
                    cut = len(word)
                    while cut > 1 and self.measure(word[:cut], font) > max_width:
                        cut -= 1
                    lines.append(word[:cut])
                    word = word[cut:]
                line = word
            lines.append(line)
        while lines and not lines[-1]:
            lines.pop()
        return lines

    def fit(self, text, weight, max_size, min_size, max_height, spacing, width=None):
        """Самый крупный кегль, при котором текст влезает в max_height.
        Возвращает (шрифт, строки, высота строки)."""
        width = width or self.content_w
        size = max_size
        while True:
            font = _font(weight, size)
            lines = self.wrap(text, font, width)
            line_height = round(size * spacing)
            if len(lines) * line_height <= max_height or size <= min_size:
                return font, lines, line_height
            size -= 2

    def text_block(self, lines, font, line_height, y, fill, x=None, width=None) -> int:
        """Рисует строки с учётом выравнивания, возвращает y под блоком."""
        left = PADDING if x is None else x
        width = width or self.content_w
        for line in lines:
            line_x = left + (width - self.measure(line, font)) / 2 if self.center else left
            self.draw_run(line_x, y, line, font, fill)
            y += line_height
        return y

    def emoji(self, sequence: str, size: int, y: int, x: int | None = None) -> bool:
        glyph = _emoji_image(sequence, size) if sequence else None
        if glyph is None:
            return False
        if x is None:
            x = (self.w - glyph.width) // 2 if self.center else PADDING
        self.image.alpha_composite(glyph, (x, y))
        return True

    def accent_bar(self, y: int) -> None:
        x = (self.w - 96) // 2 if self.center else PADDING
        self.draw.rounded_rectangle((x, y, x + 96, y + 12), radius=6, fill=self.accent)

    def footer(self, handle: str, index: int, total: int) -> None:
        font = _font("Medium", 30)
        y = self.h - PADDING + 10
        if handle:
            self.draw.text((PADDING, y), handle, font=font, fill=self.theme.muted, anchor="ls")
        if self.design["show_counter"]:
            self.draw.text((self.w - PADDING, y), f"{index + 1}/{total}", font=font, fill=self.theme.muted, anchor="rs")

    def bottom(self) -> int:
        """Нижняя граница контента (над подвалом)."""
        return self.h - PADDING - FOOTER_SPACE

    def png(self) -> bytes:
        buffer = io.BytesIO()
        self.image.convert("RGB").save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


# --------------------------------------------------------- макеты ---------

def _header(c: Canvas, slide: dict, index: int) -> int:
    """Шапка слайда-пункта: крупный номер и/или эмодзи. Возвращает y под ней."""
    y = PADDING + 10
    show_number = c.design["show_numbers"]
    emoji = slide.get("emoji", "")
    if c.center:
        if emoji and c.emoji(emoji, 120, y):
            return y + 160
        if show_number:
            number_font = _font("ExtraBold", 110)
            c.draw.text((c.w // 2, y), f"{index:02d}", font=number_font, fill=c.accent, anchor="mt")
            return y + 160
        return y + 20
    has_header = False
    if show_number:
        c.draw.text((PADDING - 6, y), f"{index:02d}", font=_font("ExtraBold", 120), fill=c.accent)
        has_header = True
    if emoji:
        has_header = c.emoji(emoji, 120, y + 6, x=c.w - PADDING - 120) or has_header
    return y + 190 if has_header else y + 20


def _render_cover(c: Canvas, slide: dict, total: int) -> None:
    s = c.scale
    top, bottom = PADDING + 20, c.bottom() - (70 if c.design["show_swipe"] else 0)
    emoji_size = 150 if c.h > 1100 else 110
    emoji_block = emoji_size + 50 if slide.get("emoji") and _emoji_image(slide["emoji"], emoji_size) else 0
    # Бюджет высоты — от реально свободного места (в квадрате его заметно
    # меньше): ~65% заголовку, остаток подзаголовку.
    free = bottom - top - emoji_block - 40
    title_font, title_lines, title_lh = c.fit(slide["title"], "ExtraBold", int(112 * s), 48, int(free * 0.65), 1.12)
    body_budget = free - len(title_lines) * title_lh - 44
    body_font, body_lines, body_lh = c.fit(slide.get("body", ""), "Regular", 46, 26, max(body_budget, 0), 1.4)
    if body_lines and len(body_lines) * body_lh > body_budget:
        body_lines = []  # совсем не влезает даже мелким — лучше без подзаголовка, чем наезд
    body_block = 44 + len(body_lines) * body_lh if body_lines else 0
    block = emoji_block + 40 + len(title_lines) * title_lh + body_block
    y = max(top, top + (bottom - top - block) // 2)

    if emoji_block:
        c.emoji(slide["emoji"], emoji_size, y)
        y += emoji_block
    c.accent_bar(y)
    y += 40
    y = c.text_block(title_lines, title_font, title_lh, y, c.theme.text)
    if body_lines:
        c.text_block(body_lines, body_font, body_lh, y + 44, c.theme.muted)

    if c.design["show_swipe"]:
        font = _font("SemiBold", 36)
        x, anchor = ((c.w // 2, "ms") if c.center else (PADDING, "ls"))
        c.draw.text((x, c.h - PADDING - 70), "Листайте →", font=font, fill=c.accent, anchor=anchor)


def _render_text(c: Canvas, slide: dict, index: int) -> None:
    y = _header(c, slide, index)
    title_font, title_lines, title_lh = c.fit(slide["title"], "Bold", int(76 * c.scale), 44, int(c.h * 0.25), 1.18)
    y = c.text_block(title_lines, title_font, title_lh, y, c.theme.text)
    if slide.get("body"):
        y += 40
        body_font, body_lines, body_lh = c.fit(slide["body"], "Regular", 46, 28, c.bottom() - y, 1.45)
        c.text_block(body_lines, body_font, body_lh, y, c.theme.text)


def _render_list(c: Canvas, slide: dict, index: int) -> None:
    y = _header(c, slide, index)
    title_font, title_lines, title_lh = c.fit(slide["title"], "Bold", int(70 * c.scale), 44, int(c.h * 0.2), 1.18)
    y = c.text_block(title_lines, title_font, title_lh, y, c.theme.text) + 36

    items = [item for item in slide.get("items", []) if item.strip()]
    if not items:
        return
    gap, pad_x, pad_y, marker_w = 16, 32, 22, 64
    available = c.bottom() - y
    text_width = c.content_w - 2 * pad_x - marker_w
    # Общий кегль для всех пунктов — уменьшаем, пока весь список не влезет
    for size in range(42, 25, -2):
        font = _font("Medium", size)
        line_height = round(size * 1.3)
        wrapped = []
        for item in items:
            marker = first_emoji(item) if item.startswith(first_emoji(item) or "\0") else ""
            text = item[len(marker):].strip() if marker else item
            wrapped.append((marker, c.wrap(text, font, text_width)))
        total = sum(len(lines) * line_height + 2 * pad_y for _, lines in wrapped) + gap * (len(items) - 1)
        if total <= available:
            break

    for marker, lines in wrapped:
        box_h = len(lines) * line_height + 2 * pad_y
        c.surface_box((PADDING, y, c.w - PADDING, y + box_h), radius=24)
        marker_y = y + pad_y + (line_height - size) // 2
        if not (marker and c.emoji(marker, size + 4, marker_y - 2, x=PADDING + pad_x)):
            dot = size // 2
            cx, cy = PADDING + pad_x + dot // 2, y + pad_y + line_height // 2 - dot // 2
            c.draw.ellipse((cx, cy, cx + dot, cy + dot), fill=c.accent)
        text_x = PADDING + pad_x + marker_w
        for i, line in enumerate(lines):
            c.draw_run(text_x, y + pad_y + i * line_height, line, font, c.theme.text)
        y += box_h + gap


def _render_stat(c: Canvas, slide: dict, index: int) -> None:
    y = PADDING + 30
    if slide.get("emoji"):
        c.emoji(slide["emoji"], 110, y, x=None if c.center else c.w - PADDING - 110)
        if c.center:
            y += 150
    value = slide.get("value") or "—"
    size = 300
    while size > 110 and c.measure(value, _font("ExtraBold", size)) > c.content_w:
        size -= 10
    value_font = _font("ExtraBold", size)
    y += 40 if not c.center else 0
    c.text_block([value], value_font, round(size * 1.05), y, c.accent)
    y += round(size * 1.1) + 20

    title_font, title_lines, title_lh = c.fit(slide["title"], "Bold", int(64 * c.scale), 40, int(c.h * 0.2), 1.2)
    y = c.text_block(title_lines, title_font, title_lh, y, c.theme.text)
    if slide.get("body"):
        body_font, body_lines, body_lh = c.fit(slide["body"], "Regular", 42, 28, c.bottom() - y - 30, 1.45)
        c.text_block(body_lines, body_font, body_lh, y + 30, c.theme.muted)


def _render_quote(c: Canvas, slide: dict, index: int) -> None:
    y = PADDING + 10
    quote_mark = _font("ExtraBold", 260)
    x, anchor = ((c.w // 2, "mt") if c.center else (PADDING - 10, "lt"))
    c.draw.text((x, y), "«", font=quote_mark, fill=c.accent, anchor=anchor)
    y += 250
    author_space = 110 if slide.get("title") else 0
    body_font, body_lines, body_lh = c.fit(
        slide.get("body") or slide["title"], "SemiBold", int(62 * c.scale), 34, c.bottom() - y - author_space, 1.3
    )
    y = c.text_block(body_lines, body_font, body_lh, y, c.theme.text)
    if slide.get("body") and slide.get("title"):
        author_font = _font("Regular", 38)
        c.text_block([f"— {slide['title']}"], author_font, 50, y + 40, c.theme.muted)


def _render_cta(c: Canvas, slide: dict, index: int) -> None:
    button = slide.get("value") or "Сохраните пост"
    button_font = _font("SemiBold", 40)
    emoji_size = 140 if c.h > 1100 else 110

    top, bottom = PADDING + 20, c.bottom()
    emoji_block = emoji_size + 50 if slide.get("emoji") and _emoji_image(slide["emoji"], emoji_size) else 0
    free = bottom - top - emoji_block - 60 - 104  # минус отступ и сама кнопка
    title_font, title_lines, title_lh = c.fit(slide["title"], "ExtraBold", int(88 * c.scale), 44, int(free * 0.55), 1.15)
    body_budget = free - len(title_lines) * title_lh - 36
    body_font, body_lines, body_lh = c.fit(slide.get("body", ""), "Regular", 44, 26, max(body_budget, 0), 1.45)
    if body_lines and len(body_lines) * body_lh > body_budget:
        body_lines = []
    body_block = 36 + len(body_lines) * body_lh if body_lines else 0
    block = emoji_block + len(title_lines) * title_lh + body_block + 60 + 104
    y = max(top, top + (bottom - top - block) // 2)

    if emoji_block:
        c.emoji(slide["emoji"], emoji_size, y)
        y += emoji_block
    y = c.text_block(title_lines, title_font, title_lh, y, c.theme.text)
    if body_lines:
        y = c.text_block(body_lines, body_font, body_lh, y + 36, c.theme.muted)
    y += 60

    button_w = min(c.content_w, round(c.measure(button, button_font)) + 112)
    x = (c.w - button_w) // 2 if c.center else PADDING
    c.draw.rounded_rectangle((x, y, x + button_w, y + 104), radius=52, fill=c.accent)
    c.draw_run(x + (button_w - c.measure(button, button_font)) / 2, y + 26, button, button_font, c.theme.on_accent)


RENDERERS = {
    "text": _render_text,
    "list": _render_list,
    "stat": _render_stat,
    "quote": _render_quote,
    "cta": _render_cta,
}


def render_slide(slide: dict, index: int, total: int, theme_name: str, handle: str = "", design: dict | None = None) -> Canvas:
    canvas = Canvas(THEMES.get(theme_name, THEMES["light"]), normalize_design(design))
    layout = slide.get("layout") or ("cover" if index == 0 else "text")
    if layout == "cover":
        _render_cover(canvas, slide, total)
    else:
        RENDERERS.get(layout, _render_text)(canvas, slide, index)
    canvas.footer(handle, index, total)
    return canvas


def render_slide_png(*args, **kwargs) -> bytes:
    return render_slide(*args, **kwargs).png()


def render_preview_jpeg(*args, width: int = 540, **kwargs) -> bytes:
    """Уменьшенное превью для живого редактора — быстрее отдаётся и грузится."""
    image = render_slide(*args, **kwargs).image.convert("RGB")
    image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def render_carousel(slides: list[dict], theme_name: str, handle: str = "", design: dict | None = None) -> list[bytes]:
    return [render_slide_png(slide, i, len(slides), theme_name, handle, design) for i, slide in enumerate(slides)]
