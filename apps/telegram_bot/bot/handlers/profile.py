from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User
from asgiref.sync import sync_to_async

from .. import keyboards, services
from ..states import MiscFlow
from ..ui import render, start_wizard

router = Router(name="profile")


async def _profile_view(tg_user: User) -> tuple[str, object]:
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
    return text, keyboards.profile_keyboard(has_email=bool(stats.email))


@router.message(Command("profile"))
async def show_profile(message: Message, state: FSMContext) -> None:
    text, kb = await _profile_view(message.from_user)
    await start_wizard(message, state, text, kb)


@router.callback_query(F.data == keyboards.MENU_PROFILE_CB)
async def show_profile_cb(callback: CallbackQuery, state: FSMContext) -> None:
    text, kb = await _profile_view(callback.from_user)
    await render(callback, state, text, kb)


@router.callback_query(F.data == keyboards.CHANGE_EMAIL_CB)
async def change_email_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MiscFlow.waiting_new_email)
    await render(callback, state, "Введите новый email:", keyboards.cancel_keyboard())


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
        await render(message, state, error_text, keyboards.cancel_keyboard())
        return

    await state.clear()
    text, kb = await _profile_view(message.from_user)
    await render(message, state, f"✅ Email обновлён.\n\n{text}", kb)


@router.message(MiscFlow.waiting_new_email)
async def change_email_invalid(message: Message, state: FSMContext) -> None:
    await render(message, state, "Пришлите email текстом.", keyboards.cancel_keyboard())
