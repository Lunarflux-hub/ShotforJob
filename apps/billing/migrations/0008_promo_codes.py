from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0007_rename_robokassa_to_payanyway"),
    ]

    operations = [
        migrations.CreateModel(
            name="PromoCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "code",
                    models.CharField(
                        help_text="Промокод, который вводит пользователь (регистр не важен)",
                        max_length=32,
                        unique=True,
                    ),
                ),
                (
                    "discount_type",
                    models.CharField(
                        choices=[("percent", "Процент от цены"), ("fixed", "Фиксированная сумма")],
                        default="percent",
                        max_length=10,
                    ),
                ),
                (
                    "discount_value",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Для типа «Процент» — число от 0 до 100, для «Фиксированная сумма» — сумма в рублях",
                        max_digits=10,
                    ),
                ),
                (
                    "valid_from",
                    models.DateTimeField(
                        default=django.utils.timezone.now, help_text="С какого момента промокод действует"
                    ),
                ),
                (
                    "valid_until",
                    models.DateTimeField(help_text="До какого момента промокод действует (обязательно)"),
                ),
                (
                    "max_uses",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Максимум успешных оплат по этому промокоду всего. Пусто — без ограничения.",
                        null=True,
                    ),
                ),
                (
                    "max_uses_per_user",
                    models.PositiveIntegerField(
                        default=1, help_text="Сколько раз один пользователь может использовать этот промокод."
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "packages",
                    models.ManyToManyField(
                        blank=True,
                        help_text="К каким тарифам применяется. Пусто — применяется ко всем тарифам.",
                        related_name="promo_codes",
                        to="billing.generationpackage",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="payment",
            name="promo_code",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments",
                to="billing.promocode",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="discount_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=10),
        ),
    ]
