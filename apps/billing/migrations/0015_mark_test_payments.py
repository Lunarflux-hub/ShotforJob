"""
1) Помечает тестовыми существующие платежи сотрудников (is_staff) и платежи
   на сумму меньше 10 ₽ — то же правило, что services.is_test_payment
   применяет к новым платежам. Уже помеченные не трогаются.
2) Все уже оплаченные платежи считаются «отправленными» в Метрику, чтобы
   открытие старой страницы чека не записало покупку задним числом.

Откат — без изменения данных (RunPython.noop): какие из платежей были
тестовыми до миграции, по данным уже не восстановить, а сами поля
purchase_reported_at и т.п. удаляются откатом 0014. Миграция при этом
откатывается без ошибок.
"""
from decimal import Decimal

from django.db import migrations
from django.db.models import F, Q
from django.db.models.functions import Coalesce


def forward(apps, schema_editor):
    Payment = apps.get_model("billing", "Payment")
    Payment.objects.filter(is_test=False).filter(
        Q(user__is_staff=True) | Q(amount__lt=Decimal("10"))
    ).update(is_test=True)
    Payment.objects.filter(status="paid", purchase_reported_at__isnull=True).update(
        purchase_reported_at=Coalesce(F("paid_at"), F("created_at"))
    )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0014_payment_analytics"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
