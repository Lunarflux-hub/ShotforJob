from decimal import Decimal

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


class PromoCode(models.Model):
    """Промокод со скидкой на один или несколько пакетов, действующий ограниченный срок."""

    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Процент от цены"
        FIXED = "fixed", "Фиксированная сумма"

    code = models.CharField(
        max_length=32,
        unique=True,
        help_text="Промокод, который вводит пользователь (регистр не важен)",
    )
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT)
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Для типа «Процент» — число от 0 до 100, для «Фиксированная сумма» — сумма в рублях",
    )
    packages = models.ManyToManyField(
        GenerationPackage,
        blank=True,
        related_name="promo_codes",
        help_text="К каким тарифам применяется. Пусто — применяется ко всем тарифам.",
    )
    valid_from = models.DateTimeField(default=timezone.now, help_text="С какого момента промокод действует")
    valid_until = models.DateTimeField(help_text="До какого момента промокод действует (обязательно)")
    max_uses = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Максимум успешных оплат по этому промокоду всего. Пусто — без ограничения.",
    )
    max_uses_per_user = models.PositiveIntegerField(
        default=1,
        help_text="Сколько раз один пользователь может использовать этот промокод.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.discount_type == self.DiscountType.PERCENT:
            return f"{self.code} (-{self.discount_value}%)"
        return f"{self.code} (-{self.discount_value} ₽)"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.discount_type == self.DiscountType.PERCENT:
            if self.discount_value is not None and not (0 < self.discount_value <= 100):
                errors["discount_value"] = "Процент скидки должен быть больше 0 и не больше 100."
        elif self.discount_value is not None and self.discount_value <= 0:
            errors["discount_value"] = "Сумма скидки должна быть больше 0."
        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            errors["valid_until"] = "Дата окончания должна быть позже даты начала."
        if errors:
            raise ValidationError(errors)

    def is_valid_now(self) -> bool:
        now = timezone.now()
        return self.is_active and self.valid_from <= now <= self.valid_until

    def applies_to(self, package: "GenerationPackage") -> bool:
        return not self.packages.exists() or self.packages.filter(pk=package.pk).exists()

    def compute_discount(self, base_amount):
        """Возвращает (итоговая_сумма, размер_скидки), не уходя ниже нуля."""
        if self.discount_type == self.DiscountType.PERCENT:
            discount = (base_amount * self.discount_value / Decimal("100")).quantize(Decimal("0.01"))
        else:
            discount = self.discount_value
        discount = min(discount, base_amount)
        return base_amount - discount, discount


class Payment(models.Model):
    """Один счёт = один MNT_TRANSACTION_ID в PayAnyWay (Moneta.ru)."""

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
    promo_code = models.ForeignKey(
        PromoCode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    is_test = models.BooleanField(default=False)

    payanyway_operation_id = models.CharField(max_length=64, blank=True)  # MNT_OPERATION_ID
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