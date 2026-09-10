from django.contrib import admin
from django.utils import timezone

from .models import GenerationPackage, Payment, GenerationLedgerEntry, PromoCode


@admin.register(GenerationPackage)
class GenerationPackageAdmin(admin.ModelAdmin):
    list_display = ("title", "price", "first_purchase_price", "generations", "is_active", "sort_order")
    list_editable = ("price", "first_purchase_price", "generations", "is_active", "sort_order")
    search_fields = ("title",)


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount_type",
        "discount_value",
        "packages_display",
        "valid_from",
        "valid_until",
        "status_display",
        "used_count",
        "max_uses",
    )
    list_filter = ("is_active", "discount_type", "valid_until")
    search_fields = ("code",)
    filter_horizontal = ("packages",)
    list_editable = ("discount_value",)
    fields = (
        "code",
        "discount_type",
        "discount_value",
        "packages",
        "valid_from",
        "valid_until",
        "max_uses",
        "max_uses_per_user",
        "is_active",
    )

    def save_model(self, request, obj, form, change):
        obj.code = obj.code.strip().upper()
        obj.full_clean()
        super().save_model(request, obj, form, change)

    @admin.display(description="Тарифы")
    def packages_display(self, obj):
        packages = list(obj.packages.all())
        if not packages:
            return "Все тарифы"
        return ", ".join(p.title for p in packages)

    @admin.display(description="Использовано")
    def used_count(self, obj):
        return obj.payments.filter(status=Payment.Status.PAID).count()

    @admin.display(description="Статус", boolean=False)
    def status_display(self, obj):
        if not obj.is_active:
            return "Отключён"
        now = timezone.now()
        if now < obj.valid_from:
            return "Ещё не начался"
        if now > obj.valid_until:
            return "Истёк"
        return "Активен"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "package", "amount", "discount_amount", "promo_code",
        "generations_granted", "status", "created_at", "paid_at",
    )
    list_filter = ("status", "is_test", "created_at", "promo_code")
    search_fields = ("user__username", "user__email", "id")
    readonly_fields = ("raw_result_payload",)


@admin.register(GenerationLedgerEntry)
class GenerationLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "kind", "amount", "balance_after", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("user__username", "user__email")