from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User
from asgiref.sync import sync_to_async

from .. import keyboards, services

router = Router(name="history")

STATUS_EMOJI = {
    "pending": "⏳",
    "processing": "⚙️",
    "done": "✅",
    "failed": "❌",
}


async def _show_history(message: Message, tg_user: User) -> None:
    profile = await sync_to_async(services.get_or_create_profile)(
        tg_user.id, tg_user.username or ""
    )
    orders = await sync_to_async(services.get_recent_orders)(profile.user)

    if not orders:
        await message.answer("У вас пока нет заказов.")
        return

    for order in orders:
        emoji = STATUS_EMOJI.get(order.status, "•")
        text = (
            f"{emoji} {order.style.name} — {order.get_status_display()}\n"
            f"{order.created_at.strftime('%d.%m.%Y %H:%M')}"
        )
        markup = keyboards.order_photo_keyboard(order.id) if order.status == "done" else None
        await message.answer(text, reply_markup=markup)


@router.message(Command("history"))
async def show_history(message: Message) -> None:
    await _show_history(message, message.from_user)


@router.callback_query(F.data == keyboards.MENU_HISTORY_CB)
async def show_history_cb(callback: CallbackQuery) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_history(callback.message, callback.from_user)
    await callback.answer()


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
