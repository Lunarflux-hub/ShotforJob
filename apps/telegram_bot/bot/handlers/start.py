from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from asgiref.sync import sync_to_async

from .. import keyboards
from .. import services

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await sync_to_async(services.get_or_create_profile)(
        message.from_user.id, message.from_user.username or ""
    )
    await message.answer(
        "Привет! Я бот ShotForJob — сгенерирую профессиональное фото по вашим "
        "снимкам. Выберите действие в меню ниже.",
        reply_markup=keyboards.main_menu(),
    )


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
