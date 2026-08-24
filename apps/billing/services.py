"""
Экономика генераций: весь код, который меняет баланс пользователя, должен
идти через эти функции — они держат UserBalance.generations и
GenerationLedgerEntry строго в синхроне под блокировкой строки.

Почему не считать баланс суммой/последней записью ledger на лету:
GenerationLedgerEntry — insert-only, у него нет "последней строки", которую
можно залочить SELECT ... FOR UPDATE, чтобы сериализовать конкурентные
списания (новая строка просто добавляется рядом). Поэтому материализованный
UserBalance — обязателен: именно его строку мы лочим.
"""
from django.db import transaction

from .models import GenerationLedgerEntry, UserBalance


class InsufficientBalanceError(Exception):
    """Недостаточно генераций на балансе для списания."""

    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required
        super().__init__(f"balance={balance}, required={required}")


def get_balance(user) -> int:
    balance = UserBalance.objects.filter(user=user).first()
    return balance.generations if balance else 0


def _get_or_create_locked_balance(user) -> UserBalance:
    """Должно вызываться только внутри transaction.atomic()."""
    balance, _ = UserBalance.objects.get_or_create(user=user)
    # Перечитываем ту же строку с блокировкой (get_or_create не лочит при create-hit).
    return UserBalance.objects.select_for_update().get(pk=balance.pk)


@transaction.atomic
def credit_generations(user, amount: int, *, kind=GenerationLedgerEntry.Kind.TOPUP, payment=None) -> UserBalance:
    """Начисляет `amount` генераций (используется при оплате пакета)."""
    if amount <= 0:
        raise ValueError("amount must be positive")

    balance = _get_or_create_locked_balance(user)
    balance.generations += amount
    balance.save(update_fields=["generations", "updated_at"])

    GenerationLedgerEntry.objects.create(
        user=user,
        kind=kind,
        amount=amount,
        balance_after=balance.generations,
        payment=payment,
    )
    return balance


@transaction.atomic
def spend_generation(user, order, amount: int = 1) -> UserBalance:
    """
    Атомарно списывает `amount` генераций перед постановкой заказа в очередь.
    Бросает InsufficientBalanceError, если баланса не хватает — вызывающий
    код должен создавать Order/ставить Celery-задачу только после успешного
    списания.
    Возврат при неудачной генерации НЕ выполняется (продуктовое решение) —
    генерация считается использованной попыткой.
    """
    if amount <= 0:
        raise ValueError("amount must be positive")

    balance = _get_or_create_locked_balance(user)
    if balance.generations < amount:
        raise InsufficientBalanceError(balance.generations, amount)

    balance.generations -= amount
    balance.save(update_fields=["generations", "updated_at"])

    GenerationLedgerEntry.objects.create(
        user=user,
        kind=GenerationLedgerEntry.Kind.SPEND,
        amount=-amount,
        balance_after=balance.generations,
        order=order,
    )
    return balance
