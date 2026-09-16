from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from asgiref.sync import sync_to_async
from django.conf import settings

from .. import keyboards, services

router = Router(name="balance")


@router.message(F.text == keyboards.MAIN_MENU_BALANCE)
@router.message(Command("balance"))
async def show_balance(message: Message) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(
        message.from_user.id, message.from_user.username or ""
    )
    balance = await sync_to_async(services.get_user_balance)(profile.user)
    await message.answer(
        f"💰 У вас {balance} ген. на балансе.\n\n"
        f"Пополнить баланс пока можно на сайте: {settings.FRONTEND_URL}/workstation"
    )
