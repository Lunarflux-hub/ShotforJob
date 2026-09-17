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

# Сообщение, от которого «форкнулся» текущий мастер (например, баннер
# /start, от которого стартовала «Новая генерация» новым сообщением) —
# чтобы при отмене вернуться туда, а не плодить сообщения в чате.
PARENT_CHAT_ID = "parent_chat_id"
PARENT_MSG_ID = "parent_msg_id"
PARENT_IS_PHOTO = "parent_is_photo"


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


async def finish_flow(state: FSMContext) -> None:
    """Как state.clear(), но сохраняет id отслеживаемого сообщения (WIZARD_*).
    Нужно там, где очистка идёт ПОСЛЕ render()/return_to_parent(): иначе
    следующий start_wizard() не найдёт, какое сообщение запомнить родителем
    (см. _remember_parent), и «Новая генерация» опять начнёт плодить сообщения."""
    data = await state.get_data()
    keep = {key: data[key] for key in (WIZARD_CHAT_ID, WIZARD_MSG_ID, WIZARD_IS_PHOTO) if key in data}
    await state.set_state(None)
    await state.set_data(keep)


async def _remember_parent(state: FSMContext) -> None:
    """Если уже отслеживалось сообщение — запоминаем его как «родителя»
    нового мастера, чтобы return_to_parent() знал, куда вернуться при отмене."""
    data = await state.get_data()
    chat_id, msg_id = data.get(WIZARD_CHAT_ID), data.get(WIZARD_MSG_ID)
    if chat_id and msg_id:
        await state.update_data(
            **{
                PARENT_CHAT_ID: chat_id,
                PARENT_MSG_ID: msg_id,
                PARENT_IS_PHOTO: data.get(WIZARD_IS_PHOTO, False),
            }
        )


async def start_wizard(
    message: Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Осознанно отправляет НОВОЕ сообщение (например, старт «Новой генерации»
    из главного меню) и начинает отслеживать его для последующих render()."""
    await _remember_parent(state)
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
    await _remember_parent(state)
    sent = await message.answer_photo(FSInputFile(photo_path), caption=caption, reply_markup=reply_markup)
    await state.update_data(
        **{WIZARD_CHAT_ID: sent.chat.id, WIZARD_MSG_ID: sent.message_id, WIZARD_IS_PHOTO: True}
    )


async def return_to_parent(
    event: CallbackQuery | Message,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Если у текущего отслеживаемого сообщения есть «родитель» (мастер был
    начат новым сообщением поверх него, см. _remember_parent) — удаляет
    текущее сообщение и продолжает навигацию в родителе, чтобы не плодить
    сообщения в чате. Возвращает False, если родителя нет (тогда вызывающий
    код сам решает, как рендерить — например, обычным render() на месте)."""
    data = await state.get_data()
    parent_chat_id = data.get(PARENT_CHAT_ID)
    parent_msg_id = data.get(PARENT_MSG_ID)
    if not (parent_chat_id and parent_msg_id):
        return False

    bot = event.bot
    child_chat_id = data.get(WIZARD_CHAT_ID)
    child_msg_id = data.get(WIZARD_MSG_ID)
    if (
        child_chat_id
        and child_msg_id
        and (child_chat_id, child_msg_id) != (parent_chat_id, parent_msg_id)
    ):
        try:
            await bot.delete_message(chat_id=child_chat_id, message_id=child_msg_id)
        except TelegramBadRequest:
            pass  # уже удалено пользователем/устарело — не страшно

    is_photo = data.get(PARENT_IS_PHOTO, False)
    try:
        if is_photo:
            await bot.edit_message_caption(
                chat_id=parent_chat_id, message_id=parent_msg_id, caption=text, reply_markup=reply_markup
            )
        else:
            await bot.edit_message_text(
                text, chat_id=parent_chat_id, message_id=parent_msg_id, reply_markup=reply_markup
            )
        await state.update_data(
            **{WIZARD_CHAT_ID: parent_chat_id, WIZARD_MSG_ID: parent_msg_id, WIZARD_IS_PHOTO: is_photo}
        )
    except TelegramBadRequest:
        # Родителя не отредактировать (удалён/устарел) — шлём новым сообщением,
        # чтобы пользователь не остался без ответа.
        sent = await bot.send_message(chat_id=parent_chat_id, text=text, reply_markup=reply_markup)
        await state.update_data(
            **{WIZARD_CHAT_ID: sent.chat.id, WIZARD_MSG_ID: sent.message_id, WIZARD_IS_PHOTO: False}
        )

    if isinstance(event, CallbackQuery):
        await event.answer()
    return True
