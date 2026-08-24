from django.conf import settings
from django.db import models
from django.utils import timezone


class GenerationPackage(models.Model):
    """Пакет генераций, доступный для покупки (кнопки на фронте)."""
    title = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="RUB")
    generations = models.PositiveIntegerField(help_text="Сколько генераций даёт этот пакет")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    first_purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Спеццена для первой покупки пользователя (акция). Пусто — без акции.",
    )

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.title} – {self.generations} генераций"


class Payment(models.Model):
    """Один счёт = один InvId в Robokassa."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает оплаты"
        PAID = "paid", "Оплачен"
        FAILED = "failed", "Не оплачен"
        EXPIRED = "expired", "Истёк"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments"
    )
    package = models.ForeignKey(
        GenerationPackage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)   # OutSum
    currency = models.CharField(max_length=3, default="RUB")
    generations_granted = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    is_test = models.BooleanField(default=False)

    robokassa_operation_id = models.CharField(max_length=64, blank=True)
    raw_result_payload = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Payment #{self.id} – {self.user} – {self.amount}"


class UserBalance(models.Model):
    """
    Кэш текущего баланса генераций пользователя. Источник правды для быстрого
    чтения; GenerationLedgerEntry остаётся неизменяемым журналом-аудитом.
    Обновляется только внутри services.py под select_for_update(), чтобы
    конкурентные списания/начисления не гонялись друг с другом.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="balance",
        primary_key=True,
    )
    generations = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} — {self.generations} ген."


class GenerationLedgerEntry(models.Model):
    """Неизменяемый журнал начислений/списаний генераций – источник правды для баланса."""

    class Kind(models.TextChoices):
        TOPUP = "topup", "Пополнение"
        SPEND = "spend", "Списание"
        REFUND = "refund", "Возврат"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generation_entries"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.IntegerField()          # положительный для пополнения, отрицательный для списания
    balance_after = models.IntegerField()
    payment = models.ForeignKey(
        Payment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    order = models.ForeignKey(
        "photos.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries",
        help_text="Заказ, на который списана генерация (только для kind=spend)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} – {self.kind} – {self.amount} (balance {self.balance_after})"