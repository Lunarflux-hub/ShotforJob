from aiogram.fsm.state import State, StatesGroup


class GenerationFlow(StatesGroup):
    choosing_style = State()
    choosing_clothing = State()
    choosing_background_type = State()
    waiting_background_color = State()
    waiting_background_image = State()
    waiting_photos = State()
    confirm = State()
