from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User
from asgiref.sync import sync_to_async

from .. import keyboards, services
from ..ui import render, start_wizard

router = Router(name="history")

STATUS_EMOJI = {
    "pending": "⏳",
    "processing": "⚙️",
    "done": "✅",
    "failed": "❌",
}


async def _history_view(tg_user: User) -> tuple[str, object]:
    profile = await sync_to_async(services.get_or_create_profile)(tg_user.id, tg_user.username or "")
    orders = await sync_to_async(services.get_recent_orders)(profile.user)

    if not orders:
        return "У вас пока нет заказов.", keyboards.back_to_menu_keyboard()

    lines = [
        f"{STATUS_EMOJI.get(order.status, '•')} {order.style.name} — {order.get_status_display()} "
        f"({order.created_at.strftime('%d.%m.%Y %H:%M')})"
        for order in orders
    ]
    text = "📜 <b>История заказов</b>\n\n" + "\n".join(lines)
    done_orders = [order for order in orders if order.status == "done"]
    return text, keyboards.history_keyboard(done_orders)


@router.message(Command("history"))
async def show_history(message: Message, state: FSMContext) -> None:
    text, kb = await _history_view(message.from_user)
    await start_wizard(message, state, text, kb)


@router.callback_query(F.data == keyboards.MENU_HISTORY_CB)
async def show_history_cb(callback: CallbackQuery, state: FSMContext) -> None:
    text, kb = await _history_view(callback.from_user)
    await render(callback, state, text, kb)


@router.callback_query(F.data.startswith("show_photo:"))
async def show_photo(callback: CallbackQuery) -> None:
    order_id = callback.data.split(":", 1)[1]
    profile = await sync_to_async(services.get_or_create_profile)(
        callback.from_user.id, callback.from_user.username or ""
    )
    url = await sync_to_async(services.get_order_photo_url)(profile.user, order_id)
    if url is None:
        await callback.answer("Фото не найдено", show_alert=True)
        return

    await callback.message.answer_photo(url)
    await callback.answer()
