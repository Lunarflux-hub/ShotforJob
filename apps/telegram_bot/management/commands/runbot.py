import asyncio
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.telegram_bot.bot.dispatcher import build_bot, build_dispatcher

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Запускает Telegram-бота в режиме long polling (отдельный процесс/контейнер)."

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN не задан в .env")

        logging.basicConfig(level=logging.INFO)
        asyncio.run(self._run())

    async def _run(self) -> None:
        bot = build_bot()
        dp = build_dispatcher()
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Telegram-бот запущен (long polling)")
        await dp.start_polling(bot)
