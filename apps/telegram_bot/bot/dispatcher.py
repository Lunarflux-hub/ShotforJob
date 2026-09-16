from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from django.conf import settings

from .handlers import balance, generation, history, profile, start, support


def build_bot() -> Bot:
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher() -> Dispatcher:
    # Redis, а не MemoryStorage: состояние диалога (какой шаг заказа сейчас
    # проходит пользователь) переживает перезапуск контейнера бота при
    # деплое.
    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(generation.router)
    dp.include_router(history.router)
    dp.include_router(balance.router)
    dp.include_router(profile.router)
    dp.include_router(support.router)

    return dp
