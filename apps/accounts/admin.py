from django.contrib import admin

from .models import UserAcquisition


@admin.register(UserAcquisition)
class UserAcquisitionAdmin(admin.ModelAdmin):
    list_display = ["user", "utm_source", "utm_medium", "utm_campaign", "yclid", "created_at"]
    list_filter = ["utm_source", "utm_medium"]
    search_fields = ["user__email", "utm_campaign", "yclid"]
    raw_id_fields = ["user"]
