from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User
from asgiref.sync import sync_to_async
from django.conf import settings

from .. import keyboards, services

router = Router(name="balance")


async def _show_balance(message: Message, tg_user: User) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(
        tg_user.id, tg_user.username or ""
    )
    balance = await sync_to_async(services.get_user_balance)(profile.user)
    await message.answer(
        f"💰 У вас {balance} ген. на балансе.\n\n"
        f"Пополнить баланс пока можно на сайте: {settings.FRONTEND_URL}/workstation"
    )


@router.message(Command("balance"))
async def show_balance(message: Message) -> None:
    await _show_balance(message, message.from_user)


@router.callback_query(F.data == keyboards.MENU_BALANCE_CB)
async def show_balance_cb(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_balance(callback.message, callback.from_user)
    await callback.answer()
