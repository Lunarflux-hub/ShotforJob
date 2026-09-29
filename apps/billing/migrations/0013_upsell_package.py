"""
Допродажа «Ещё 5 вариантов в другом стиле» — 149 ₽ за 5 генераций.
visibility=paid_only: не показывается в общем списке тарифов и продаётся
только тем, у кого уже была оплата (catalog.can_buy). Обратная миграция:
удаляется, если по нему не было платежей, иначе — деактивируется.
"""
from decimal import Decimal

from django.db import migrations

UPSELL = {
    "slug": "more5",
    "title": "Ещё 5 вариантов",
    "title_en": "5 more variations",
    "price": Decimal("149.00"),
    "generations": 5,
    "sort_order": 100,
    "visibility": "paid_only",
    "badge": "Для своих",
    "badge_en": "For customers",
    "features": "5 фото в другом стиле или образе\nВсе стили и фоны\nГенерации не сгорают",
    "features_en": "5 photos in another style or outfit\nAll styles and backgrounds\nGenerations never expire",
}


def forward(apps, schema_editor):
    Package = apps.get_model("billing", "GenerationPackage")
    Package.objects.update_or_create(
        slug=UPSELL["slug"], defaults={**UPSELL, "currency": "RUB", "is_active": True, "is_featured": False}
    )


def backward(apps, schema_editor):
    Package = apps.get_model("billing", "GenerationPackage")
    Payment = apps.get_model("billing", "Payment")
    package = Package.objects.filter(slug=UPSELL["slug"]).first()
    if package is None:
        return
    if Payment.objects.filter(package=package).exists():
        package.is_active = False
        package.save(update_fields=["is_active"])
    else:
        package.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0012_payment_unlock_result"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
