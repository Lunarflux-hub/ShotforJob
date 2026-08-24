from django.contrib import admin
from .models import GenerationPackage, Payment, GenerationLedgerEntry


@admin.register(GenerationPackage)
class GenerationPackageAdmin(admin.ModelAdmin):
    list_display = ("title", "price", "first_purchase_price", "generations", "is_active", "sort_order")
    list_editable = ("price", "first_purchase_price", "generations", "is_active", "sort_order")
    search_fields = ("title",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "package", "amount", "generations_granted", "status", "created_at", "paid_at")
    list_filter = ("status", "is_test", "created_at")
    search_fields = ("user__username", "user__email", "id")
    readonly_fields = ("raw_result_payload",)


@admin.register(GenerationLedgerEntry)
class GenerationLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "amount", "balance_after", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "user__email")