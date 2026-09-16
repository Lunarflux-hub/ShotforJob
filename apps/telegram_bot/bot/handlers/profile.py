from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User
from asgiref.sync import sync_to_async

from .. import keyboards, services
from ..states import MiscFlow

router = Router(name="profile")


async def _show_profile(message: Message, tg_user: User) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(tg_user.id, tg_user.username or "")
    stats = await sync_to_async(services.get_profile_stats)(profile.user, profile)

    email_line = stats.email or "не указан"
    text = (
        "👤 <b>Профиль</b>\n\n"
        f"Email: {email_line}\n"
        f"Баланс: {stats.balance} ген.\n"
        f"Заказов всего: {stats.orders_total} (готово: {stats.orders_done})\n"
        f"С нами с: {stats.member_since.strftime('%d.%m.%Y')}"
    )
    await message.answer(text, reply_markup=keyboards.profile_keyboard(has_email=bool(stats.email)))


@router.message(Command("profile"))
async def show_profile(message: Message) -> None:
    await _show_profile(message, message.from_user)


@router.callback_query(F.data == keyboards.MENU_PROFILE_CB)
async def show_profile_cb(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_profile(callback.message, callback.from_user)
    await callback.answer()


@router.callback_query(F.data == keyboards.CHANGE_EMAIL_CB)
async def change_email_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MiscFlow.waiting_new_email)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Введите новый email:", reply_markup=keyboards.cancel_keyboard())
    await callback.answer()


@router.message(MiscFlow.waiting_new_email, F.text)
async def change_email_finish(message: Message, state: FSMContext) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(
        message.from_user.id, message.from_user.username or ""
    )
    result = await sync_to_async(services.set_user_email)(profile.user, message.text)

    if not result.ok:
        error_text = (
            "Похоже, это не email. Проверьте адрес и пришлите ещё раз."
            if result.error == "invalid"
            else "Этот email уже используется другим аккаунтом. Укажите другой."
        )
        await message.answer(error_text)
        return

    await state.clear()
    await message.answer("✅ Email обновлён.")
    await _show_profile(message, message.from_user)


@router.message(MiscFlow.waiting_new_email)
async def change_email_invalid(message: Message) -> None:
    await message.answer("Пришлите email текстом.")
