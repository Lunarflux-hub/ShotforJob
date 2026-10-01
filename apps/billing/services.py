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
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.db import transaction

from apps.accounts import attribution

from .models import GenerationLedgerEntry, GenerationPackage, Payment, UserBalance

# Соль для подписи ссылки оплаты (см. make_pay_link/verify_pay_link_token) —
# ссылка уходит пользователю в Telegram без сайтовой авторизации (у
# tg_-пользователей её нет), поэтому платёж адресуется по id + подписанному
# токену вместо сессии.
PAY_LINK_SALT = "billing.pay_link"


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


def lock_balance(user) -> UserBalance:
    """Публичная обёртка для вызывающего кода, которому нужно сериализовать
    решения по пользователю (например, выдачу бесплатного превью в
    photos.views.OrderCreateView). Только внутри transaction.atomic()."""
    return _get_or_create_locked_balance(user)


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


def base_amount_for(package: GenerationPackage, user) -> Decimal:
    """Цена пакета с учётом акции для первой покупки (без промокода) —
    общая для веб-топапа (views.CreateTopupView) и бот-топапа."""
    if package.first_purchase_price is not None:
        already_paid = Payment.objects.filter(user=user, status=Payment.Status.PAID).exists()
        if not already_paid:
            return package.first_purchase_price
    return package.price


TEST_AMOUNT_THRESHOLD = Decimal("10")


def is_test_payment(user, amount: Decimal) -> bool:
    """Платёж не считается реальной выручкой: тестовый режим PayAnyWay,
    сотрудник (staff) или символическая сумма меньше 10 ₽."""
    return bool(settings.PAYANYWAY_TEST_MODE or user.is_staff or amount < TEST_AMOUNT_THRESHOLD)


def create_topup_payment(user, package: GenerationPackage) -> Payment:
    """Создаёт Payment(status=pending) на полную/акционную цену пакета —
    без промокода (промокоды пока доступны только на сайте)."""
    amount = base_amount_for(package, user)
    return Payment.objects.create(
        user=user,
        package=package,
        amount=amount,
        generations_granted=package.generations,
        is_test=is_test_payment(user, amount),
        **attribution.fields_for_payment(user),
    )


def create_unlock_payment(user, package: GenerationPackage, result) -> Payment:
    """Платёж «скачать это фото в HD»: после подтверждения вебхук начислит
    генерации пакета и сразу спишет одну на разблокировку result
    (views.payanyway_result). Без промокода — оплата в один шаг."""
    amount = base_amount_for(package, user)
    return Payment.objects.create(
        user=user,
        package=package,
        amount=amount,
        generations_granted=package.generations,
        is_test=is_test_payment(user, amount),
        unlock_result=result,
        **attribution.fields_for_payment(user),
    )


# Ссылка «оплатить и скачать в HD» из письма-напоминания: открывается без
# входа на сайт (человек часто читает почту на другом устройстве), поэтому
# адресуется подписанным токеном с id результата и пользователя.
UNLOCK_LINK_SALT = "billing.unlock_link"
UNLOCK_LINK_MAX_AGE = 7 * 24 * 3600


def make_unlock_link(result) -> str:
    token = signing.dumps({"r": result.id, "u": result.order.user_id}, salt=UNLOCK_LINK_SALT)
    return f"{settings.FRONTEND_URL}/billing/unlock/{result.id}/?t={token}"


def read_unlock_link_token(result_id: int, token: str) -> int | None:
    """id пользователя из токена или None, если токен чужой/подделан/устарел."""
    try:
        value = signing.loads(token, salt=UNLOCK_LINK_SALT, max_age=UNLOCK_LINK_MAX_AGE)
    except signing.BadSignature:
        return None
    if not isinstance(value, dict) or value.get("r") != result_id:
        return None
    return value.get("u")


def make_pay_link(payment: Payment) -> str:
    """Подписанная ссылка на views.BotPayRedirectView — открывает
    автоотправляемую форму на PayAnyWay без сайтовой авторизации."""
    token = signing.dumps(payment.id, salt=PAY_LINK_SALT)
    return f"{settings.FRONTEND_URL}/billing/pay/{payment.id}/?t={token}"


def verify_pay_link_token(payment_id: int, token: str, max_age: int = 24 * 3600) -> bool:
    try:
        value = signing.loads(token, salt=PAY_LINK_SALT, max_age=max_age)
    except signing.BadSignature:
        return False
    return value == payment_id


def get_payment_status(user, payment_id: int) -> str | None:
    payment = Payment.objects.filter(id=payment_id, user=user).first()
    return payment.status if payment else None
