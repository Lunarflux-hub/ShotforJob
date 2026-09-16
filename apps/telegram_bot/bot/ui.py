"""
Общий помощник для «мастеров» из нескольких шагов (выбор стиля/одежды/фона,
профиль, поддержка): вместо того чтобы слать новое сообщение на каждый шаг,
редактируем одно и то же сообщение бота — чат не засоряется.

Редактировать можно только сообщения самого бота. Когда шаг инициирован
нажатием на инлайн-кнопку (CallbackQuery), это всегда `callback.message` —
редактируем его напрямую. Когда шаг инициирован сообщением от пользователя
(он написал email/hex-код или прислал фото), редактируем сообщение бота,
id которого сохранён в FSM-данных предыдущим вызовом render().
"""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

WIZARD_CHAT_ID = "wizard_chat_id"
WIZARD_MSG_ID = "wizard_msg_id"


async def render(
    event: CallbackQuery | Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            pass  # текст/клавиатура не изменились — ничего страшного
        await state.update_data(**{WIZARD_CHAT_ID: event.message.chat.id, WIZARD_MSG_ID: event.message.message_id})
        await event.answer()
        return

    data = await state.get_data()
    chat_id = data.get(WIZARD_CHAT_ID)
    msg_id = data.get(WIZARD_MSG_ID)
    if chat_id and msg_id:
        try:
            await event.bot.edit_message_text(
                text, chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup
            )
            return
        except TelegramBadRequest:
            pass  # сообщение удалено/устарело — упадём в отправку нового ниже

    sent = await event.answer(text, reply_markup=reply_markup)
    await state.update_data(**{WIZARD_CHAT_ID: sent.chat.id, WIZARD_MSG_ID: sent.message_id})


async def start_wizard(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Осознанно отправляет НОВОЕ сообщение (например, старт «Новой генерации»
    из главного меню) и начинает отслеживать его для последующих render()."""
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(**{WIZARD_CHAT_ID: sent.chat.id, WIZARD_MSG_ID: sent.message_id})
