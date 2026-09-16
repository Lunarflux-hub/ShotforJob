from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from asgiref.sync import sync_to_async
from django.conf import settings

from .. import keyboards, services

router = Router(name="start")

SUPPORT_LINE = (
    "☁️ <i>Если у вас есть вопросы или возникла проблема — обратитесь в нашу поддержку.</i>"
)


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

    await message.answer(
        f"{_welcome_text()}\n\nВыберите действие:\n\n{SUPPORT_LINE}",
        reply_markup=keyboards.main_menu(),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@router.callback_query(F.data == keyboards.MENU_HOME_CB)
async def go_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Выберите действие:", reply_markup=keyboards.main_menu())
    await callback.answer()


@router.message(Command("cancel"))
@router.callback_query(F.data == "cancel")
async def cmd_cancel(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = "Отменено. Что дальше?"
    if isinstance(event, CallbackQuery):
        await event.message.edit_reply_markup(reply_markup=None)
        await event.message.answer(text, reply_markup=keyboards.main_menu())
        await event.answer()
    else:
        await event.answer(text, reply_markup=keyboards.main_menu())
