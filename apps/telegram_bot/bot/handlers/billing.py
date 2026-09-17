from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from asgiref.sync import sync_to_async

from .. import keyboards, services
from ..ui import render

router = Router(name="billing")


async def _current_profile(tg_user):
    return await sync_to_async(services.get_or_create_profile)(tg_user.id, tg_user.username or "")


@router.callback_query(F.data == keyboards.MENU_TOPUP_CB)
async def show_tariffs(callback: CallbackQuery, state: FSMContext) -> None:
    profile = await _current_profile(callback.from_user)
    tariffs = await sync_to_async(services.list_tariffs)(profile.user)
    if not tariffs:
        await render(callback, state, "Пакеты сейчас недоступны, попробуйте позже.", keyboards.back_to_menu_keyboard())
        return
    await render(callback, state, "💳 Выберите пакет генераций:", keyboards.tariffs_keyboard(tariffs))


@router.callback_query(F.data.startswith("topup:pkg:"))
async def create_payment(callback: CallbackQuery, state: FSMContext) -> None:
    package_id = int(callback.data.split(":")[2])
    profile = await _current_profile(callback.from_user)
    result = await sync_to_async(services.create_bot_payment)(profile.user, package_id)

    if result.error:
        await callback.answer("Пакет недоступен, выберите другой", show_alert=True)
        return

    text = (
        f"💳 Пакет: {result.generations} ген. за {result.amount:.0f} ₽\n\n"
        "Нажмите «Оплатить», чтобы перейти на страницу PayAnyWay. "
        "После оплаты генерации зачислятся автоматически, и я пришлю уведомление сюда."
    )
    await render(callback, state, text, keyboards.payment_keyboard(result.pay_url, result.payment_id))


@router.callback_query(F.data.startswith("topup:check:"))
async def check_payment(callback: CallbackQuery, state: FSMContext) -> None:
    payment_id = int(callback.data.split(":")[2])
    profile = await _current_profile(callback.from_user)
    payment_status = await sync_to_async(services.get_bot_payment_status)(profile.user, payment_id)

    if payment_status == "paid":
        balance = await sync_to_async(services.get_user_balance)(profile.user)
        await render(
            callback, state,
            f"✅ Оплата подтверждена! Баланс: {balance} ген.",
            keyboards.back_to_menu_keyboard(),
        )
        return

    await callback.answer(
        "Платёж пока не подтверждён. Если вы уже оплатили — подождите немного и проверьте снова.",
        show_alert=True,
    )
