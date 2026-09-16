"""
Общий помощник для «мастеров» из нескольких шагов (выбор стиля/одежды/фона,
профиль, поддержка): вместо того чтобы слать новое сообщение на каждый шаг,
редактируем одно и то же сообщение бота — чат не засоряется.

Редактировать можно только сообщения самого бота. Когда шаг инициирован
нажатием на инлайн-кнопку (CallbackQuery), это всегда `callback.message` —
редактируем его напрямую. Когда шаг инициирован сообщением от пользователя
(он написал email/hex-код или прислал фото), редактируем сообщение бота,
id которого сохранён в FSM-данных предыдущим вызовом render().

Отслеживаемое сообщение может оказаться фото с подписью (например,
приветственное сообщение с баннером) — тогда редактируем caption, а не text;
какой вариант нужен, помним в FSM-данных (WIZARD_IS_PHOTO).
"""
from __future__ import annotations

from pathlib import Path

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message

WIZARD_CHAT_ID = "wizard_chat_id"
WIZARD_MSG_ID = "wizard_msg_id"
WIZARD_IS_PHOTO = "wizard_is_photo"


async def render(
    event: CallbackQuery | Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if isinstance(event, CallbackQuery):
        msg = event.message
        is_photo = bool(msg.photo)
        try:
            if is_photo:
                await msg.edit_caption(caption=text, reply_markup=reply_markup)
            else:
                await msg.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            # Не смогли отредактировать (например, подпись/текст не влезли) —
            # шлём новым сообщением, чтобы пользователь не завис на месте.
            sent = await msg.answer(text, reply_markup=reply_markup)
            await state.update_data(
                **{WIZARD_CHAT_ID: sent.chat.id, WIZARD_MSG_ID: sent.message_id, WIZARD_IS_PHOTO: False}
            )
            await event.answer()
            return

        await state.update_data(
            **{WIZARD_CHAT_ID: msg.chat.id, WIZARD_MSG_ID: msg.message_id, WIZARD_IS_PHOTO: is_photo}
        )
        await event.answer()
        return

    data = await state.get_data()
    chat_id = data.get(WIZARD_CHAT_ID)
    msg_id = data.get(WIZARD_MSG_ID)
    is_photo = data.get(WIZARD_IS_PHOTO, False)
    if chat_id and msg_id:
        try:
            if is_photo:
                await event.bot.edit_message_caption(
                    chat_id=chat_id, message_id=msg_id, caption=text, reply_markup=reply_markup
                )
            else:
                await event.bot.edit_message_text(
                    text, chat_id=chat_id, message_id=msg_id, reply_markup=reply_markup
                )
            return
        except TelegramBadRequest:
            pass  # сообщение удалено/устарело/не влезло — упадём в отправку нового ниже

    sent = await event.answer(text, reply_markup=reply_markup)
    await state.update_data(
        **{WIZARD_CHAT_ID: sent.chat.id, WIZARD_MSG_ID: sent.message_id, WIZARD_IS_PHOTO: False}
    )


async def start_wizard(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Осознанно отправляет НОВОЕ сообщение (например, старт «Новой генерации»
    из главного меню) и начинает отслеживать его для последующих render()."""
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(
        **{WIZARD_CHAT_ID: sent.chat.id, WIZARD_MSG_ID: sent.message_id, WIZARD_IS_PHOTO: False}
    )


async def start_wizard_photo(
    message: Message,
    state: FSMContext,
    photo_path: Path,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Как start_wizard(), но первым сообщением — фото с подписью (например,
    приветственный баннер). Дальнейшие render() будут редактировать caption."""
    sent = await message.answer_photo(FSInputFile(photo_path), caption=caption, reply_markup=reply_markup)
    await state.update_data(
        **{WIZARD_CHAT_ID: sent.chat.id, WIZARD_MSG_ID: sent.message_id, WIZARD_IS_PHOTO: True}
    )
