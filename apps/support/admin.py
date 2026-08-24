from django.contrib import admin

from .models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ["id", "email", "status", "ip_address", "created_at"]
    list_filter = ["status"]
    search_fields = ["email", "message"]
    readonly_fields = ["id", "created_at", "updated_at"]
