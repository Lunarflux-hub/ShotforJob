"""
Отзыв о генерации: под сообщением с готовым фото (см.
apps.telegram_bot.notifications.notify_order_result) ряд звёзд 1–5. Нажатие
сразу сохраняет оценку и предлагает дописать комментарий одним сообщением
(или пропустить).

Редактируем подпись самого сообщения с фото напрямую, а не через ui.render():
пользователь может оценить результат посреди другого мастера (например,
уже начал новую генерацию), и перехватывать отслеживаемое мастером
сообщение (WIZARD_*) здесь нельзя.
"""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from asgiref.sync import sync_to_async

from apps.telegram_bot.notifications import ORDER_RESULT_CAPTION

from .. import keyboards, services
from ..states import MiscFlow

router = Router(name="review")

REVIEW_ORDER_ID = "review_order_id"
REVIEW_CHAT_ID = "review_chat_id"
REVIEW_MSG_ID = "review_msg_id"
REVIEW_RATING = "review_rating"


def _thanks_caption(rating: int) -> str:
    return f"{ORDER_RESULT_CAPTION}\n\nВаша оценка: {'⭐' * rating}\nСпасибо за отзыв! 💙"


async def _edit_result_message(bot, chat_id: int, msg_id: int, caption: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=caption, reply_markup=markup)
    except TelegramBadRequest:
        pass  # сообщение удалено/устарело — отзыв всё равно сохранён


@router.callback_query(F.data.startswith(f"{keyboards.REVIEW_RATE_CB}:"))
async def review_rate(callback: CallbackQuery, state: FSMContext) -> None:
    _, order_id, raw_rating = callback.data.split(":")
    rating = int(raw_rating)
    if not 1 <= rating <= 5:
        await callback.answer()
        return

    profile = await sync_to_async(services.get_or_create_profile)(
        callback.from_user.id, callback.from_user.username or ""
    )
    saved = await sync_to_async(services.save_bot_review)(profile.user, order_id, rating=rating)
    if saved is None:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    msg = callback.message
    # Посреди другого мастера (выбор стиля, ввод email и т.п.) не перехватываем
    # ввод текста под комментарий — просто благодарим за оценку.
    if await state.get_state() not in (None, MiscFlow.waiting_review_comment.state):
        await _edit_result_message(
            callback.bot, msg.chat.id, msg.message_id,
            _thanks_caption(rating), keyboards.order_result_keyboard(order_id, ask_review=False),
        )
        await callback.answer("Спасибо за оценку!")
        return

    prompt = (
        "Что нам стоит улучшить? Напишите одним сообщением — мы читаем каждый отзыв."
        if rating <= 3
        else "Хотите добавить пару слов? Напишите одним сообщением."
    )
    await state.set_state(MiscFlow.waiting_review_comment)
    await state.update_data(
        **{
            REVIEW_ORDER_ID: order_id,
            REVIEW_CHAT_ID: msg.chat.id,
            REVIEW_MSG_ID: msg.message_id,
            REVIEW_RATING: rating,
        }
    )
    await _edit_result_message(
        callback.bot, msg.chat.id, msg.message_id,
        f"{ORDER_RESULT_CAPTION}\n\nВаша оценка: {'⭐' * rating}\n{prompt}",
        keyboards.review_comment_keyboard(order_id),
    )
    await callback.answer()


async def _finish_review(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _edit_result_message(
        event.bot, data[REVIEW_CHAT_ID], data[REVIEW_MSG_ID],
        _thanks_caption(data[REVIEW_RATING]),
        keyboards.order_result_keyboard(data[REVIEW_ORDER_ID], ask_review=False),
    )
    await state.set_state(None)
    await state.update_data(
        **{key: None for key in (REVIEW_ORDER_ID, REVIEW_CHAT_ID, REVIEW_MSG_ID, REVIEW_RATING)}
    )


@router.message(MiscFlow.waiting_review_comment, F.text)
async def review_comment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    profile = await sync_to_async(services.get_or_create_profile)(
        message.from_user.id, message.from_user.username or ""
    )
    await sync_to_async(services.save_bot_review)(
        profile.user, data[REVIEW_ORDER_ID], comment=message.text[:2000]
    )
    await _finish_review(message, state)
    await message.answer("Спасибо за отзыв! 💙", reply_markup=keyboards.back_to_menu_keyboard())


@router.callback_query(MiscFlow.waiting_review_comment, F.data.startswith(f"{keyboards.REVIEW_SKIP_CB}:"))
async def review_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await _finish_review(callback, state)
    await callback.answer("Спасибо за оценку!")


@router.callback_query(F.data.startswith(f"{keyboards.REVIEW_SKIP_CB}:"))
async def review_skip_stale(callback: CallbackQuery) -> None:
    """«Без комментария» после того, как состояние уже сброшено (например,
    пользователь успел уйти в меню) — просто убираем кнопку."""
    order_id = callback.data.split(":", 1)[1]
    try:
        await callback.message.edit_reply_markup(
            reply_markup=keyboards.order_result_keyboard(order_id, ask_review=False)
        )
    except TelegramBadRequest:
        pass
    await callback.answer()
