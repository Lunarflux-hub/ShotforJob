from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from asgiref.sync import sync_to_async

from .. import keyboards, services
from ..states import MiscFlow

router = Router(name="support")


async def _start_support(message: Message, tg_user, state: FSMContext) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(tg_user.id, tg_user.username or "")
    if not profile.user.email:
        await message.answer(
            "Чтобы связаться с поддержкой, сначала укажите email в профиле.",
            reply_markup=keyboards.profile_keyboard(has_email=False),
        )
        return

    await state.set_state(MiscFlow.waiting_support_message)
    await message.answer(
        f"Опишите проблему одним сообщением (минимум 10 символов) — ответим на {profile.user.email}.",
        reply_markup=keyboards.cancel_keyboard(),
    )


@router.message(Command("support"))
async def support_command(message: Message, state: FSMContext) -> None:
    await _start_support(message, message.from_user, state)


@router.callback_query(F.data == keyboards.MENU_SUPPORT_CB)
async def support_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _start_support(callback.message, callback.from_user, state)
    await callback.answer()


@router.message(MiscFlow.waiting_support_message, F.text)
async def support_message(message: Message, state: FSMContext) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(
        message.from_user.id, message.from_user.username or ""
    )
    result = await sync_to_async(services.create_support_ticket)(profile.user.email, message.text)

    if not result.ok:
        errors = result.errors or {}
        detail = next(iter(errors.get("message", [])), None) or "Не удалось отправить обращение, попробуйте ещё раз."
        await message.answer(detail)
        return

    await state.clear()
    await message.answer(
        f"Спасибо! Обращение отправлено, ответим на {profile.user.email}.",
        reply_markup=keyboards.main_menu(),
    )


@router.message(MiscFlow.waiting_support_message)
async def support_message_invalid(message: Message) -> None:
    await message.answer("Опишите проблему текстом.")
