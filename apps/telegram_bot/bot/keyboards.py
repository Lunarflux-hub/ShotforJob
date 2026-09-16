"""
Клавиатуры бота. Наборы значений для одежды/фона зеркалят choices из
apps/photos/serializers.py::OrderCreateSerializer — при изменении списка
там нужно поправить и здесь.
"""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

MAIN_MENU_NEW_ORDER = "🖼 Новая генерация"
MAIN_MENU_HISTORY = "📜 История заказов"
MAIN_MENU_BALANCE = "💰 Баланс"

CLOTHING_LABELS = {
    "casual": "Повседневная",
    "formal": "Деловая",
    "sport": "Спортивная",
    "jacket": "Пиджак",
    "shirt": "Рубашка",
}

BACKGROUND_LABELS = {
    "office": "Офис",
    "nature": "Природа",
    "solid": "Однотонный фон",
    "upload": "Своё изображение",
}

BACKGROUND_COLOR_PRESETS = {
    "white": "#FFFFFF",
    "gray": "#808080",
    "blue": "#0066FF",
    "black": "#000000",
}

SKIP = "skip"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=MAIN_MENU_NEW_ORDER)],
            [KeyboardButton(text=MAIN_MENU_HISTORY), KeyboardButton(text=MAIN_MENU_BALANCE)],
        ],
        resize_keyboard=True,
    )


def styles_keyboard(styles) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=style.name, callback_data=f"style:{style.id}")]
        for style in styles
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def clothing_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"clothing:{value}")]
        for value, label in CLOTHING_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="Пропустить", callback_data=f"clothing:{SKIP}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def background_type_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"bg:{value}")]
        for value, label in BACKGROUND_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="Пропустить", callback_data=f"bg:{SKIP}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def background_color_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=name, callback_data=f"bgcolor:{hexval}")]
        for name, hexval in BACKGROUND_COLOR_PRESETS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def photos_keyboard(count: int) -> InlineKeyboardMarkup:
    rows = []
    if count >= 1:
        rows.append([InlineKeyboardButton(text=f"✅ Готово ({count} фото)", callback_data="photos_done")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Сгенерировать", callback_data="confirm_yes")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        ]
    )


def order_photo_keyboard(order_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Показать фото", callback_data=f"show_photo:{order_id}")]]
    )
