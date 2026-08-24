from django.contrib import admin

from .models import SocialAccount


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ["provider", "provider_user_id", "email", "user", "created_at"]
    list_filter = ["provider"]
    search_fields = ["email", "provider_user_id", "user__username"]
