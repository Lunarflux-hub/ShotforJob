import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User
from asgiref.sync import sync_to_async
from django.conf import settings

from .. import keyboards, services
from ..states import GenerationFlow
from ..ui import render, start_wizard

router = Router(name="generation")


async def _current_profile(user):
    return await sync_to_async(services.get_or_create_profile)(user.id, user.username or "")


async def _new_order_entry(answer_target: Message, tg_user: User, state: FSMContext) -> None:
    """Сам факт нажатия «Новая генерация» осознанно шлёт новое сообщение —
    дальше все шаги мастера редактируют именно его. Баланс проверяем сразу,
    до выбора стиля/одежды/фото: если пополнять всё равно придётся, пусть
    пользователь увидит кнопку оплаты как можно раньше, а не после того как
    заполнит всю анкету. Email просим не здесь, а перед самым запуском
    генерации (см. _finalize_order) — он не нужен раньше и не должен стоять
    между пользователем и оплатой."""
    profile = await _current_profile(tg_user)

    balance = await sync_to_async(services.get_user_balance)(profile.user)
    if balance < 1:
        await start_wizard(
            answer_target, state,
            f"Недостаточно генераций на балансе (сейчас: {balance}). Пополните баланс:",
            keyboards.balance_keyboard(),
        )
        return

    styles = await sync_to_async(services.list_active_styles)()
    if not styles:
        await answer_target.answer("Стили сейчас недоступны, попробуйте позже.")
        return
    await state.set_state(GenerationFlow.choosing_style)
    await start_wizard(answer_target, state, "Выберите стиль генерации:", keyboards.styles_keyboard(styles))


@router.message(Command("new"))
async def start_new_order(message: Message, state: FSMContext) -> None:
    await _new_order_entry(message, message.from_user, state)


@router.callback_query(F.data == keyboards.MENU_NEW_ORDER_CB)
async def start_new_order_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _new_order_entry(callback.message, callback.from_user, state)
    await callback.answer()


@router.message(GenerationFlow.waiting_email, F.text)
async def receive_order_email(message: Message, state: FSMContext) -> None:
    profile = await _current_profile(message.from_user)
    result = await sync_to_async(services.set_user_email)(profile.user, message.text)

    if not result.ok:
        error_text = (
            "Похоже, это не email. Проверьте адрес и пришлите ещё раз."
            if result.error == "invalid"
            else "Этот email уже используется другим аккаунтом. Укажите другой."
        )
        await render(message, state, error_text, keyboards.cancel_keyboard())
        return

    await _finalize_order(message, state, message.from_user)


@router.message(GenerationFlow.waiting_email)
async def receive_order_email_invalid(message: Message, state: FSMContext) -> None:
    await render(message, state, "Пришлите email текстом.", keyboards.cancel_keyboard())


@router.callback_query(GenerationFlow.choosing_style, F.data.startswith("style:"))
async def choose_style(callback: CallbackQuery, state: FSMContext) -> None:
    style_id = int(callback.data.split(":", 1)[1])
    style = await sync_to_async(services.get_style)(style_id)
    if style is None:
        await callback.answer("Стиль недоступен, выберите другой", show_alert=True)
        return

    await state.update_data(style_id=style.id, style_name=style.name)
    await state.set_state(GenerationFlow.choosing_clothing)
    await render(callback, state, "Какая одежда?", keyboards.clothing_keyboard())


@router.callback_query(GenerationFlow.choosing_clothing, F.data.startswith("clothing:"))
async def choose_clothing(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    clothing = "" if value == keyboards.SKIP else value
    await state.update_data(clothing=clothing)
    await state.set_state(GenerationFlow.choosing_background_type)
    await render(callback, state, "Какой фон?", keyboards.background_type_keyboard())


@router.callback_query(GenerationFlow.choosing_background_type, F.data.startswith("bg:"))
async def choose_background_type(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]

    if value == keyboards.SKIP:
        await state.update_data(background_type="", background_color="", background_image_file_id=None)
        await _ask_for_photos(callback, state)
    elif value == "solid":
        await state.update_data(background_type="solid")
        await state.set_state(GenerationFlow.waiting_background_color)
        await render(
            callback, state,
            "Выберите цвет фона или пришлите свой hex-код (например #0066FF):",
            keyboards.background_color_keyboard(),
        )
    elif value == "upload":
        await state.update_data(background_type="upload")
        await state.set_state(GenerationFlow.waiting_background_image)
        await render(
            callback, state,
            "🖼 Пришлите фото, которое использовать как фон.",
            keyboards.cancel_keyboard(),
        )
    else:
        await state.update_data(background_type=value, background_color="", background_image_file_id=None)
        await _ask_for_photos(callback, state)


HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@router.callback_query(GenerationFlow.waiting_background_color, F.data.startswith("bgcolor:"))
async def choose_background_color_preset(callback: CallbackQuery, state: FSMContext) -> None:
    color = callback.data.split(":", 1)[1]
    await state.update_data(background_color=color, background_image_file_id=None)
    await _ask_for_photos(callback, state)


@router.message(GenerationFlow.waiting_background_color, F.text)
async def choose_background_color_text(message: Message, state: FSMContext) -> None:
    color = (message.text or "").strip()
    if not HEX_COLOR_RE.match(color):
        await render(
            message, state,
            "Некорректный hex-код. Пример: #0066FF",
            keyboards.background_color_keyboard(),
        )
        return
    await state.update_data(background_color=color, background_image_file_id=None)
    await _ask_for_photos(message, state)


@router.message(GenerationFlow.waiting_background_image, F.photo)
async def receive_background_image(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(background_image_file_id=file_id)
    await _ask_for_photos(message, state)


@router.message(GenerationFlow.waiting_background_image)
async def receive_background_image_invalid(message: Message, state: FSMContext) -> None:
    await render(message, state, "🖼 Пришлите изображение фона как фото.", keyboards.cancel_keyboard())


async def _ask_for_photos(event: CallbackQuery | Message, state: FSMContext) -> None:
    await state.update_data(photo_file_ids=[])
    await state.set_state(GenerationFlow.waiting_photos)
    await render(
        event, state,
        f"📸 Пришлите от 1 до {settings.MAX_UPLOAD_PHOTOS} ваших фото (по одному сообщению на фото).",
        keyboards.photos_keyboard(count=0),
    )


@router.message(GenerationFlow.waiting_photos, F.photo)
async def receive_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photo_file_ids = list(data.get("photo_file_ids", []))

    if len(photo_file_ids) >= settings.MAX_UPLOAD_PHOTOS:
        await render(
            message, state,
            f"Уже загружено максимум фото ({settings.MAX_UPLOAD_PHOTOS}). "
            "Нажмите «Готово» или «Отмена».",
            keyboards.photos_keyboard(count=len(photo_file_ids)),
        )
        return

    photo_file_ids.append(message.photo[-1].file_id)
    await state.update_data(photo_file_ids=photo_file_ids)
    await render(
        message, state,
        f"📸 Фото добавлено ({len(photo_file_ids)}/{settings.MAX_UPLOAD_PHOTOS}).",
        keyboards.photos_keyboard(count=len(photo_file_ids)),
    )


@router.callback_query(GenerationFlow.waiting_photos, F.data == "photos_done")
async def photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photo_file_ids = data.get("photo_file_ids", [])
    if not photo_file_ids:
        await callback.answer("Пришлите хотя бы одно фото", show_alert=True)
        return

    await state.set_state(GenerationFlow.confirm)

    clothing_label = keyboards.CLOTHING_LABELS.get(data.get("clothing", ""), "не указана")
    background_label = keyboards.BACKGROUND_LABELS.get(data.get("background_type", ""), "не указан")
    summary = (
        f"Стиль: {data.get('style_name')}\n"
        f"Одежда: {clothing_label}\n"
        f"Фон: {background_label}\n"
        f"Фото: {len(photo_file_ids)} шт.\n\n"
        "Списать 1 генерацию и запустить создание фото?"
    )
    await render(callback, state, summary, keyboards.confirm_keyboard())


@router.callback_query(GenerationFlow.confirm, F.data == "confirm_yes")
async def confirm_order(callback: CallbackQuery, state: FSMContext) -> None:
    await _finalize_order(callback, state, callback.from_user)


async def _finalize_order(event: CallbackQuery | Message, state: FSMContext, tg_user: User) -> None:
    """Общий хвост мастера — вызывается и по кнопке «Сгенерировать», и сразу
    после того, как пользователь прислал email (см. receive_order_email).
    Проверяем баланс раньше почты: если платить всё равно придётся, не
    заставляем сначала вводить email — почту спрашиваем последней, прямо
    перед списанием, и только если её ещё нет."""
    profile = await _current_profile(tg_user)
    data = await state.get_data()

    style = await sync_to_async(services.get_style)(data["style_id"])
    if style is None:
        await state.clear()
        await render(event, state, "Стиль больше недоступен.", keyboards.main_menu())
        return

    balance = await sync_to_async(services.get_user_balance)(profile.user)
    if balance < 1:
        await state.clear()
        await render(
            event, state,
            f"Недостаточно генераций на балансе (сейчас: {balance}). Пополните баланс:",
            keyboards.balance_keyboard(),
        )
        return

    if not profile.user.email:
        await state.set_state(GenerationFlow.waiting_email)
        await render(
            event, state,
            "Для отправки результата нужен email — на него пришлём готовое фото.\n\nУкажите ваш email:",
            keyboards.cancel_keyboard(),
        )
        return

    photos = []
    for file_id in data.get("photo_file_ids", []):
        buffer = await event.bot.download(file_id)
        photos.append(services.NewOrderPhoto(filename=f"{file_id}.jpg", data=buffer.read()))

    background_image = None
    bg_file_id = data.get("background_image_file_id")
    if bg_file_id:
        buffer = await event.bot.download(bg_file_id)
        background_image = services.NewOrderPhoto(filename=f"{bg_file_id}.jpg", data=buffer.read())

    result = await sync_to_async(services.create_order_from_bot)(
        user=profile.user,
        style=style,
        clothing=data.get("clothing", ""),
        background_type=data.get("background_type", ""),
        background_color=data.get("background_color", ""),
        background_image=background_image,
        photos=photos,
    )

    await state.clear()

    if result.error == "insufficient_balance":
        # Баланс проверили выше, но кто-то мог потратить его между проверкой
        # и списанием (гонка, например второй параллельный заказ) — атомарная
        # проверка внутри create_order_from_bot страхует от двойного списания.
        text = f"Недостаточно генераций на балансе (сейчас: {result.balance}). Пополните баланс:"
        await render(event, state, text, keyboards.balance_keyboard())
        return

    text = "🚀 Заявка принята! Пришлю фото сюда, как только будет готово (обычно 1–3 минуты)."
    await render(event, state, text, keyboards.main_menu())
