from django.contrib import admin

from .models import TelegramProfile


@admin.register(TelegramProfile)
class TelegramProfileAdmin(admin.ModelAdmin):
    list_display = ("telegram_id", "telegram_username", "user", "created_at")
    search_fields = ("telegram_id", "telegram_username", "user__username")
