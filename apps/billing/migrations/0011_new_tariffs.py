"""
Новая линейка тарифов: «Старт» 1 фото — 49 ₽, «Оптимальный» 5 фото — 199 ₽
(выбран по умолчанию), «Про» 15 фото — 449 ₽.

Старые пакеты не удаляются — на них ссылаются платежи (Payment.package),
только деактивируются. Акция «первая покупка» у новых пакетов не заводится:
крючком для новичков теперь служит бесплатное превью.

Обратная миграция: новые пакеты без платежей удаляются (с платежами —
деактивируются), старые пакеты снова включаются.
"""
from decimal import Decimal

from django.db import migrations

OLD_TITLES = ["Стартовый", "Оптимальный", "Профессиональный", "Бизнес"]

NEW_PACKAGES = [
    {
        "slug": "start",
        "title": "Старт",
        "title_en": "Start",
        "price": Decimal("49.00"),
        "generations": 1,
        "sort_order": 10,
        "is_featured": False,
        "badge": "",
        "badge_en": "",
        "features": "1 деловое фото в HD\nВсе стили и фоны\nГенерации не сгорают",
        "features_en": "1 business photo in HD\nAll styles and backgrounds\nGenerations never expire",
    },
    {
        "slug": "optimal",
        "title": "Оптимальный",
        "title_en": "Optimal",
        "price": Decimal("199.00"),
        "generations": 5,
        "sort_order": 20,
        "is_featured": True,
        "badge": "Популярный",
        "badge_en": "Popular",
        "features": "5 фото в HD — на резюме, LinkedIn и соцсети\nВсе стили и фоны\nГенерации не сгорают",
        "features_en": "5 photos in HD — for your CV, LinkedIn and socials\nAll styles and backgrounds\nGenerations never expire",
    },
    {
        "slug": "pro",
        "title": "Про",
        "title_en": "Pro",
        "price": Decimal("449.00"),
        "generations": 15,
        "sort_order": 30,
        "is_featured": False,
        "badge": "",
        "badge_en": "",
        "features": "15 фото в HD\nДля портфолио или всей команды\nГенерации не сгорают",
        "features_en": "15 photos in HD\nFor a portfolio or the whole team\nGenerations never expire",
    },
]


def forward(apps, schema_editor):
    Package = apps.get_model("billing", "GenerationPackage")
    Package.objects.filter(title__in=OLD_TITLES, slug="").update(is_active=False)
    for data in NEW_PACKAGES:
        Package.objects.update_or_create(
            slug=data["slug"],
            defaults={**data, "currency": "RUB", "is_active": True, "visibility": "public"},
        )


def backward(apps, schema_editor):
    Package = apps.get_model("billing", "GenerationPackage")
    Payment = apps.get_model("billing", "Payment")
    for data in NEW_PACKAGES:
        package = Package.objects.filter(slug=data["slug"]).first()
        if package is None:
            continue
        if Payment.objects.filter(package=package).exists():
            package.is_active = False
            package.save(update_fields=["is_active"])
        else:
            package.delete()
    Package.objects.filter(title__in=OLD_TITLES, slug="").update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0010_package_storefront_fields"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
