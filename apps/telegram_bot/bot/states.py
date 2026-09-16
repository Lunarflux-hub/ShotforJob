from aiogram.fsm.state import State, StatesGroup


class GenerationFlow(StatesGroup):
    waiting_email = State()  # email ещё не задан — спрашиваем перед выбором стиля
    choosing_style = State()
    choosing_clothing = State()
    choosing_background_type = State()
    waiting_background_color = State()
    waiting_background_image = State()
    waiting_photos = State()
    confirm = State()


class MiscFlow(StatesGroup):
    waiting_new_email = State()  # смена email из профиля
    waiting_support_message = State()
