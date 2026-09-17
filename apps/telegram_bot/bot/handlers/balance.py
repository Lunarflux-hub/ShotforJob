from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User
from asgiref.sync import sync_to_async

from .. import keyboards, services
from ..ui import render, start_wizard

router = Router(name="balance")


async def _balance_text(tg_user: User) -> str:
    profile = await sync_to_async(services.get_or_create_profile)(tg_user.id, tg_user.username or "")
    balance = await sync_to_async(services.get_user_balance)(profile.user)
    return f"💰 У вас {balance} ген. на балансе."


@router.message(Command("balance"))
async def show_balance(message: Message, state: FSMContext) -> None:
    text = await _balance_text(message.from_user)
    await start_wizard(message, state, text, keyboards.balance_keyboard())


@router.callback_query(F.data == keyboards.MENU_BALANCE_CB)
async def show_balance_cb(callback: CallbackQuery, state: FSMContext) -> None:
    text = await _balance_text(callback.from_user)
    await render(callback, state, text, keyboards.balance_keyboard())
