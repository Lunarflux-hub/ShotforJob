import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User
from asgiref.sync import sync_to_async
from django.conf import settings

from .. import keyboards, services
from ..states import GenerationFlow

router = Router(name="generation")


async def _current_profile(user):
    return await sync_to_async(services.get_or_create_profile)(user.id, user.username or "")


async def _start_new_order(message: Message, state: FSMContext) -> None:
    await state.clear()
    styles = await sync_to_async(services.list_active_styles)()
    if not styles:
        await message.answer("Стили сейчас недоступны, попробуйте позже.")
        return
    await state.set_state(GenerationFlow.choosing_style)
    await message.answer("Выберите стиль генерации:", reply_markup=keyboards.styles_keyboard(styles))


async def _start_new_order_entry(message: Message, tg_user: User, state: FSMContext) -> None:
    """Email нужен, чтобы отправить готовое фото — просим его один раз, при
    первом заказе, а не на /start. Дальше меняется только через профиль."""
    profile = await _current_profile(tg_user)
    if not profile.user.email:
        await state.clear()
        await state.set_state(GenerationFlow.waiting_email)
        await message.answer(
            "Для заказа нужен email — на него пришлём готовое фото.\n\nУкажите ваш email:",
            reply_markup=keyboards.cancel_keyboard(),
        )
        return
    await _start_new_order(message, state)


@router.message(Command("new"))
async def start_new_order(message: Message, state: FSMContext) -> None:
    await _start_new_order_entry(message, message.from_user, state)


@router.callback_query(F.data == keyboards.MENU_NEW_ORDER_CB)
async def start_new_order_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_reply_markup(reply_markup=None)
    await _start_new_order_entry(callback.message, callback.from_user, state)
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
        await message.answer(error_text)
        return

    await message.answer("✅ Email сохранён.")
    await _start_new_order(message, state)


@router.message(GenerationFlow.waiting_email)
async def receive_order_email_invalid(message: Message) -> None:
    await message.answer("Пришлите email текстом.")


@router.callback_query(GenerationFlow.choosing_style, F.data.startswith("style:"))
async def choose_style(callback: CallbackQuery, state: FSMContext) -> None:
    style_id = int(callback.data.split(":", 1)[1])
    style = await sync_to_async(services.get_style)(style_id)
    if style is None:
        await callback.answer("Стиль недоступен, выберите другой", show_alert=True)
        return

    await state.update_data(style_id=style.id, style_name=style.name)
    await state.set_state(GenerationFlow.choosing_clothing)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Какая одежда?", reply_markup=keyboards.clothing_keyboard())
    await callback.answer()


@router.callback_query(GenerationFlow.choosing_clothing, F.data.startswith("clothing:"))
async def choose_clothing(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    clothing = "" if value == keyboards.SKIP else value
    await state.update_data(clothing=clothing)
    await state.set_state(GenerationFlow.choosing_background_type)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Какой фон?", reply_markup=keyboards.background_type_keyboard())
    await callback.answer()


@router.callback_query(GenerationFlow.choosing_background_type, F.data.startswith("bg:"))
async def choose_background_type(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":", 1)[1]
    await callback.message.edit_reply_markup(reply_markup=None)

    if value == keyboards.SKIP:
        await state.update_data(background_type="", background_color="", background_image_file_id=None)
        await _ask_for_photos(callback.message, state)
    elif value == "solid":
        await state.update_data(background_type="solid")
        await state.set_state(GenerationFlow.waiting_background_color)
        await callback.message.answer(
            "Выберите цвет фона или пришлите свой hex-код (например #0066FF):",
            reply_markup=keyboards.background_color_keyboard(),
        )
    elif value == "upload":
        await state.update_data(background_type="upload")
        await state.set_state(GenerationFlow.waiting_background_image)
        await callback.message.answer("Пришлите фото, которое использовать как фон.")
    else:
        await state.update_data(background_type=value, background_color="", background_image_file_id=None)
        await _ask_for_photos(callback.message, state)

    await callback.answer()


HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@router.callback_query(GenerationFlow.waiting_background_color, F.data.startswith("bgcolor:"))
async def choose_background_color_preset(callback: CallbackQuery, state: FSMContext) -> None:
    color = callback.data.split(":", 1)[1]
    await state.update_data(background_color=color, background_image_file_id=None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await _ask_for_photos(callback.message, state)
    await callback.answer()


@router.message(GenerationFlow.waiting_background_color, F.text)
async def choose_background_color_text(message: Message, state: FSMContext) -> None:
    color = (message.text or "").strip()
    if not HEX_COLOR_RE.match(color):
        await message.answer("Некорректный hex-код. Пример: #0066FF")
        return
    await state.update_data(background_color=color, background_image_file_id=None)
    await _ask_for_photos(message, state)


@router.message(GenerationFlow.waiting_background_image, F.photo)
async def receive_background_image(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(background_image_file_id=file_id)
    await _ask_for_photos(message, state)


@router.message(GenerationFlow.waiting_background_image)
async def receive_background_image_invalid(message: Message) -> None:
    await message.answer("Пришлите изображение фона как фото.")


async def _ask_for_photos(message: Message, state: FSMContext) -> None:
    await state.update_data(photo_file_ids=[])
    await state.set_state(GenerationFlow.waiting_photos)
    await message.answer(
        f"Пришлите от 1 до {settings.MAX_UPLOAD_PHOTOS} ваших фото (по одному сообщению на фото).",
        reply_markup=keyboards.photos_keyboard(count=0),
    )


@router.message(GenerationFlow.waiting_photos, F.photo)
async def receive_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photo_file_ids = list(data.get("photo_file_ids", []))

    if len(photo_file_ids) >= settings.MAX_UPLOAD_PHOTOS:
        await message.answer(
            f"Уже загружено максимум фото ({settings.MAX_UPLOAD_PHOTOS}). "
            "Нажмите «Готово» или «Отмена».",
            reply_markup=keyboards.photos_keyboard(count=len(photo_file_ids)),
        )
        return

    photo_file_ids.append(message.photo[-1].file_id)
    await state.update_data(photo_file_ids=photo_file_ids)
    await message.answer(
        f"Фото добавлено ({len(photo_file_ids)}/{settings.MAX_UPLOAD_PHOTOS}).",
        reply_markup=keyboards.photos_keyboard(count=len(photo_file_ids)),
    )


@router.callback_query(GenerationFlow.waiting_photos, F.data == "photos_done")
async def photos_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photo_file_ids = data.get("photo_file_ids", [])
    if not photo_file_ids:
        await callback.answer("Пришлите хотя бы одно фото", show_alert=True)
        return

    await state.set_state(GenerationFlow.confirm)
    await callback.message.edit_reply_markup(reply_markup=None)

    clothing_label = keyboards.CLOTHING_LABELS.get(data.get("clothing", ""), "не указана")
    background_label = keyboards.BACKGROUND_LABELS.get(data.get("background_type", ""), "не указан")
    summary = (
        f"Стиль: {data.get('style_name')}\n"
        f"Одежда: {clothing_label}\n"
        f"Фон: {background_label}\n"
        f"Фото: {len(photo_file_ids)} шт.\n\n"
        "Списать 1 генерацию и запустить создание фото?"
    )
    await callback.message.answer(summary, reply_markup=keyboards.confirm_keyboard())
    await callback.answer()


@router.callback_query(GenerationFlow.confirm, F.data == "confirm_yes")
async def confirm_order(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    style = await sync_to_async(services.get_style)(data["style_id"])
    if style is None:
        await callback.answer("Стиль больше недоступен", show_alert=True)
        await state.clear()
        return

    profile = await _current_profile(callback.from_user)

    photos = []
    for file_id in data.get("photo_file_ids", []):
        buffer = await bot.download(file_id)
        photos.append(services.NewOrderPhoto(filename=f"{file_id}.jpg", data=buffer.read()))

    background_image = None
    bg_file_id = data.get("background_image_file_id")
    if bg_file_id:
        buffer = await bot.download(bg_file_id)
        background_image = services.NewOrderPhoto(filename=f"{bg_file_id}.jpg", data=buffer.read())

    await callback.message.edit_reply_markup(reply_markup=None)

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
        await callback.message.answer(
            f"Недостаточно генераций на балансе (сейчас: {result.balance}). "
            f"Пополнить можно на сайте: {settings.FRONTEND_URL}/workstation",
            reply_markup=keyboards.main_menu(),
        )
    else:
        await callback.message.answer(
            "🚀 Заявка принята! Пришлю фото сюда, как только будет готово "
            "(обычно 1–3 минуты).",
            reply_markup=keyboards.main_menu(),
        )
    await callback.answer()
