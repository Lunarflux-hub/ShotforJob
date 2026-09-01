import hashlib
from decimal import Decimal
from django.conf import settings

MNT_ID = str(settings.PAYANYWAY_MNT_ID).strip()
INTEGRITY_CODE = str(settings.PAYANYWAY_INTEGRITY_CODE).strip()
IS_TEST = settings.PAYANYWAY_TEST_MODE
CURRENCY_CODE = str(settings.PAYANYWAY_CURRENCY_CODE).strip()
ASSISTANT_URL = "https://moneta.ru/assistant.htm"


def _fmt_sum(amount: Decimal) -> str:
    # MNT_AMOUNT: десятичные символы через точку, максимум два знака после запятой.
    return f"{amount:.2f}"


def _fmt_test_mode() -> str:
    return "1" if IS_TEST else "0"


def build_payment_request(payment, description: str, email: str | None = None) -> dict:
    """
    Готовит данные для отправки формы на MONETA.Assistant (аналог
    build_payment_request из robokassa.py). MNT_TRANSACTION_ID — это id
    платежа в нашей БД (аналог InvId).
    """
    mnt_amount = _fmt_sum(payment.amount)
    mnt_transaction_id = str(payment.id)
    mnt_test_mode = _fmt_test_mode()

    # Подпись формы оплаты (см. "Формирование платежной кнопки через
    # MONETA.Assistant" в документации PayAnyWay):
    # MD5(MNT_ID + MNT_TRANSACTION_ID + MNT_AMOUNT + MNT_CURRENCY_CODE + MNT_TEST_MODE + код)
    sign_parts = [MNT_ID, mnt_transaction_id, mnt_amount, CURRENCY_CODE, mnt_test_mode, INTEGRITY_CODE]
    signature = hashlib.md5("".join(sign_parts).encode("utf-8")).hexdigest()

    fields = {
        "MNT_ID": MNT_ID,
        "MNT_TRANSACTION_ID": mnt_transaction_id,
        "MNT_AMOUNT": mnt_amount,
        "MNT_CURRENCY_CODE": CURRENCY_CODE,
        "MNT_DESCRIPTION": description[:500],
        "MNT_TEST_MODE": mnt_test_mode,
        "MNT_SIGNATURE": signature,
    }
    # Необязательный e-mail плательщика (для чека/уведомлений на стороне Moneta.ru)
    if email:
        fields["MNT_EMAIL"] = email

    return {
        "action_url": ASSISTANT_URL,
        "method": "POST",
        "fields": fields,
    }


def verify_pay_url_signature(
    mnt_transaction_id: str,
    mnt_operation_id: str,
    mnt_amount: str,
    mnt_currency_code: str,
    mnt_subscriber_id: str,
    mnt_test_mode: str,
    signature: str,
) -> bool:
    """
    Проверка подписи запроса на Pay URL (уведомление об успешной оплате):
    MD5(MNT_ID + MNT_TRANSACTION_ID + MNT_OPERATION_ID + MNT_AMOUNT +
        MNT_CURRENCY_CODE + MNT_SUBSCRIBER_ID + MNT_TEST_MODE + код)
    """
    parts = [
        MNT_ID,
        mnt_transaction_id,
        mnt_operation_id,
        mnt_amount,
        mnt_currency_code,
        mnt_subscriber_id,
        mnt_test_mode,
        INTEGRITY_CODE,
    ]
    expected = hashlib.md5("".join(parts).encode("utf-8")).hexdigest()
    return expected.lower() == signature.lower()
