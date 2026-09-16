from django.conf import settings
from django.db import models


class TelegramProfile(models.Model):
    """
    Связывает Telegram-пользователя с Django `User`. Заводится автоматически
    при первом /start в apps.telegram_bot.bot.services.get_or_create_profile
    — бот создаёт "технического" User (username=f"tg_{telegram_id}", без
    пароля), чтобы переиспользовать общие с сайтом Order/UserBalance/
    spend_generation без дублирования бизнес-логики.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_profile",
    )
    telegram_id = models.BigIntegerField(unique=True, db_index=True)
    telegram_username = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"@{self.telegram_username or self.telegram_id}"
