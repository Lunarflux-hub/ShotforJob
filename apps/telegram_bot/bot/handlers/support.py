from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from asgiref.sync import sync_to_async

from .. import keyboards, services
from ..states import MiscFlow
from ..ui import render, start_wizard

router = Router(name="support")

SUPPORT_MENU_TEXT = "🆘 <b>Поддержка</b>\n\nВыберите, что нужно:"

FAQ_TEXT = (
    "❓ <b>Частые вопросы</b>\n\n"
    "<b>Сколько ждать результат?</b>\n"
    "Обычно 1–3 минуты после отправки фото.\n\n"
    "<b>Сколько фото нужно загрузить?</b>\n"
    "От 1 до 3 фото — чем чётче лицо видно, тем лучше результат.\n\n"
    "<b>Генерация не удалась — что делать?</b>\n"
    "Попробуйте создать заказ ещё раз. Если проблема повторяется — напишите в поддержку.\n\n"
    "<b>Как пополнить баланс генераций?</b>\n"
    "В разделе «💰 Баланс» → «💳 Пополнить баланс» — выберите пакет и оплатите по ссылке.\n\n"
    "<b>Где хранятся мои фото?</b>\n"
    "Загруженные фото автоматически удаляются в течение суток после генерации."
)


@router.message(Command("support"))
async def support_command(message: Message, state: FSMContext) -> None:
    await start_wizard(message, state, SUPPORT_MENU_TEXT, keyboards.support_menu_keyboard())


@router.callback_query(F.data == keyboards.MENU_SUPPORT_CB)
async def support_menu_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await render(callback, state, SUPPORT_MENU_TEXT, keyboards.support_menu_keyboard())


@router.callback_query(F.data == keyboards.SUPPORT_FAQ_CB)
async def support_faq(callback: CallbackQuery, state: FSMContext) -> None:
    await render(callback, state, FAQ_TEXT, keyboards.faq_keyboard())


@router.callback_query(F.data == keyboards.SUPPORT_WRITE_CB)
async def support_write_start(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(
        callback.from_user.id, callback.from_user.username or ""
    )
    if not profile.user.email:
        await render(
            callback, state,
            "Чтобы связаться с поддержкой, сначала укажите email в профиле.",
            keyboards.profile_keyboard(has_email=False),
        )
        return

    await state.set_state(MiscFlow.waiting_support_message)
    await render(
        callback, state,
        f"✍️ Опишите проблему одним сообщением (минимум 10 символов) — ответим на {profile.user.email}.",
        keyboards.cancel_keyboard(),
    )


@router.message(MiscFlow.waiting_support_message, F.text)
async def support_message(message: Message, state: FSMContext) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(
        message.from_user.id, message.from_user.username or ""
    )
    result = await sync_to_async(services.create_support_ticket)(profile.user.email, message.text)

    if not result.ok:
        errors = result.errors or {}
        detail = next(iter(errors.get("message", [])), None) or "Не удалось отправить обращение, попробуйте ещё раз."
        await render(message, state, detail, keyboards.cancel_keyboard())
        return

    await state.clear()
    await render(
        message, state,
        f"Спасибо! Обращение отправлено, ответим на {profile.user.email}.",
        keyboards.back_to_menu_keyboard(),
    )


@router.message(MiscFlow.waiting_support_message)
async def support_message_invalid(message: Message, state: FSMContext) -> None:
    await render(message, state, "Опишите проблему текстом.", keyboards.cancel_keyboard())
