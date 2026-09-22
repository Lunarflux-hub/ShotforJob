"""
Клавиатуры бота. Наборы значений для одежды/фона зеркалят choices из
apps/photos/serializers.py::OrderCreateSerializer — при изменении списка
там нужно поправить и здесь.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from django.conf import settings

MAIN_MENU_NEW_ORDER = "🖼 Новая генерация"
MAIN_MENU_HISTORY = "📜 История заказов"
MAIN_MENU_BALANCE = "💰 Баланс"
MAIN_MENU_PROFILE = "👤 Профиль"
MAIN_MENU_SUPPORT = "🆘 Поддержка"
MAIN_MENU_REVIEWS = "⭐ Отзывы"

MENU_NEW_ORDER_CB = "menu:new"
MENU_HISTORY_CB = "menu:history"
MENU_BALANCE_CB = "menu:balance"
MENU_PROFILE_CB = "menu:profile"
MENU_SUPPORT_CB = "menu:support"
MENU_HOME_CB = "menu:home"
MENU_TOPUP_CB = "menu:topup"
CHANGE_EMAIL_CB = "profile:change_email"
SUPPORT_FAQ_CB = "support:faq"
SUPPORT_WRITE_CB = "support:write"
REVIEW_RATE_CB = "review"  # review:<order_id>:<1..5>
REVIEW_SKIP_CB = "review_skip"  # review_skip:<order_id>

# value -> (иконка+подпись для кнопки, подпись без иконки для текстового резюме)
CLOTHING_LABELS = {
    "casual": "👕 Повседневная",
    "formal": "🤵 Деловая",
    "sport": "🏃 Спортивная",
    "jacket": "🧥 Пиджак",
    "shirt": "👔 Рубашка",
}

BACKGROUND_LABELS = {
    "office": "🏢 Офис",
    "nature": "🌳 Природа",
    "solid": "🎨 Однотонный фон",
    "upload": "🖼 Своё изображение",
}

BACKGROUND_COLOR_PRESETS = {
    "⬜ Белый": "#FFFFFF",
    "◽ Серый": "#808080",
    "🟦 Синий": "#0066FF",
    "⬛ Чёрный": "#000000",
}

SKIP = "skip"


def main_menu() -> InlineKeyboardMarkup:
    """Навигация — кнопки под сообщением, а не постоянная клавиатура снизу."""
    rows = [
        [InlineKeyboardButton(text=MAIN_MENU_NEW_ORDER, callback_data=MENU_NEW_ORDER_CB)],
        [
            InlineKeyboardButton(text=MAIN_MENU_HISTORY, callback_data=MENU_HISTORY_CB),
            InlineKeyboardButton(text=MAIN_MENU_BALANCE, callback_data=MENU_BALANCE_CB),
        ],
        [
            InlineKeyboardButton(text=MAIN_MENU_PROFILE, callback_data=MENU_PROFILE_CB),
            InlineKeyboardButton(text=MAIN_MENU_SUPPORT, callback_data=MENU_SUPPORT_CB),
        ],
    ]
    if settings.TELEGRAM_REVIEWS_CHANNEL_URL:
        rows.append([InlineKeyboardButton(text=MAIN_MENU_REVIEWS, url=settings.TELEGRAM_REVIEWS_CHANNEL_URL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data=MENU_HOME_CB)]])


def balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data=MENU_TOPUP_CB)],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data=MENU_HOME_CB)],
        ]
    )


def _format_price(price) -> str:
    return f"{price:.0f} ₽" if price == price.to_integral_value() else f"{price} ₽"


def tariffs_keyboard(tariffs) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{tariff.title} — {tariff.generations} ген. — {_format_price(tariff.price)}"
                + (" 🎁" if tariff.is_promo else ""),
                callback_data=f"topup:pkg:{tariff.id}",
            )
        ]
        for tariff in tariffs
    ]
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data=MENU_HOME_CB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_keyboard(pay_url: str, payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=pay_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"topup:check:{payment_id}")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data=MENU_HOME_CB)],
        ]
    )


def profile_keyboard(*, has_email: bool) -> InlineKeyboardMarkup:
    change_label = "✏️ Изменить email" if has_email else "✏️ Указать email"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=change_label, callback_data=CHANGE_EMAIL_CB)],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data=MENU_HOME_CB)],
        ]
    )


def support_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❓ FAQ", callback_data=SUPPORT_FAQ_CB),
                InlineKeyboardButton(text="✍️ Написать в поддержку", callback_data=SUPPORT_WRITE_CB),
            ],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data=MENU_HOME_CB)],
        ]
    )


def faq_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=MENU_SUPPORT_CB)]]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]])


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
    rows.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"clothing:{SKIP}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def background_type_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"bg:{value}")]
        for value, label in BACKGROUND_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"bg:{SKIP}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def background_color_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"bgcolor:{hexval}")]
        for label, hexval in BACKGROUND_COLOR_PRESETS.items()
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


def order_result_keyboard(order_id, *, ask_review: bool = True) -> InlineKeyboardMarkup:
    """Кнопки под сообщением с готовым результатом (см.
    apps.telegram_bot.notifications.notify_order_result) — «Скинуть ещё раз»
    работает и спустя долгое время: заново берёт presigned-ссылку на S3, а не
    полагается на то, что файл ещё жив в кеше Telegram. Пока отзыв не
    оставлен (ask_review=True), сверху ряд звёзд для оценки (bot/handlers/review.py)."""
    rows = []
    if ask_review:
        rows.append(
            [
                InlineKeyboardButton(text=f"{n}⭐", callback_data=f"{REVIEW_RATE_CB}:{order_id}:{n}")
                for n in range(1, 6)
            ]
        )
    rows.append([InlineKeyboardButton(text="📷 Скинуть ещё раз", callback_data=f"show_photo:{order_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data=MENU_HOME_CB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def review_comment_keyboard(order_id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Без комментария", callback_data=f"{REVIEW_SKIP_CB}:{order_id}")],
        ]
    )


def history_keyboard(done_orders: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"📷 Фото от {order.created_at.strftime('%d.%m')}",
                callback_data=f"show_photo:{order.id}",
            )
        ]
        for order in done_orders
    ]
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data=MENU_HOME_CB)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
