from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from asgiref.sync import sync_to_async
from django.conf import settings

from .. import keyboards, services
from ..ui import render, start_wizard, start_wizard_photo

router = Router(name="start")

SUPPORT_LINE = (
    "☁️ <i>Если у вас есть вопросы или возникла проблема — обратитесь в нашу поддержку.</i>"
)

WELCOME_IMAGE_PATH = Path(__file__).resolve().parents[2] / "assets" / "welcome.png"


def _welcome_text() -> str:
    offer_url = f"{settings.FRONTEND_URL}/policy/?doc=offer"
    return (
        "👋 <b>Добро пожаловать в ShotforJob!</b>\n\n"
        "Я сгенерирую профессиональное фото по вашим снимкам.\n\n"
        f'Перед использованием ознакомьтесь с <a href="{offer_url}">публичной офертой</a>.'
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await sync_to_async(services.get_or_create_profile)(
        message.from_user.id, message.from_user.username or ""
    )

    text = f"{_welcome_text()}\n\nВыберите действие:\n\n{SUPPORT_LINE}"
    if WELCOME_IMAGE_PATH.exists():
        await start_wizard_photo(message, state, WELCOME_IMAGE_PATH, text, keyboards.main_menu())
    else:
        await start_wizard(message, state, text, keyboards.main_menu())


@router.callback_query(F.data == keyboards.MENU_HOME_CB)
async def go_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await render(callback, state, "Выберите действие:", keyboards.main_menu())


@router.message(Command("cancel"))
@router.callback_query(F.data == "cancel")
async def cmd_cancel(event: Message | CallbackQuery, state: FSMContext) -> None:
    await render(event, state, "Отменено. Что дальше?", keyboards.main_menu())
    await state.clear()
