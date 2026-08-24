import hashlib
import json
from decimal import Decimal
from django.conf import settings

MERCHANT_LOGIN = settings.ROBOKASSA_MERCHANT_LOGIN
PASSWORD_1 = settings.ROBOKASSA_PASSWORD_1
PASSWORD_2 = settings.ROBOKASSA_PASSWORD_2
IS_TEST = settings.ROBOKASSA_TEST_MODE
PAY_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"


def _fmt_sum(amount: Decimal) -> str:
    return f"{amount:.2f}"


def build_receipt(description: str, amount: Decimal) -> str:
    receipt = {
        "sno": settings.ROBOKASSA_SNO,
        "items": [
            {
                "name": description[:128],
                "quantity": 1,
                "sum": float(amount),
                "tax": settings.ROBOKASSA_TAX,
            }
        ],
    }
    return json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))

def build_payment_request(payment, description: str, email: str | None = None) -> dict:
    out_sum = _fmt_sum(payment.amount)
    inv_id = str(payment.id)
    receipt = build_receipt(description, payment.amount)   # <-- чек

    # Строка подписи с чеком
    sign_parts = [MERCHANT_LOGIN, out_sum, inv_id, receipt, PASSWORD_1]
    signature = hashlib.md5(":".join(sign_parts).encode("utf-8")).hexdigest()

    fields = {
        "MerchantLogin": MERCHANT_LOGIN,
        "OutSum": out_sum,
        "InvId": inv_id,
        "Description": description[:100],
        "Receipt": receipt,
        "SignatureValue": signature,
        "Culture": "ru",
    }
    if IS_TEST:
        fields["IsTest"] = "1"
    if email:
        fields["Email"] = email

    return {
        "action_url": PAY_URL,
        "method": "POST",
        "fields": fields,
    }


def verify_result_signature(out_sum: str, inv_id: str, signature: str, receipt: str | None = None) -> bool:
    parts = [out_sum, inv_id]
    if receipt:
        parts.append(receipt)
    parts.append(PASSWORD_2)
    expected = hashlib.md5(":".join(parts).encode("utf-8")).hexdigest()
    return expected.lower() == signature.lower()


def verify_redirect_signature(out_sum: str, inv_id: str, signature: str) -> bool:
    expected = hashlib.md5(
        f"{out_sum}:{inv_id}:{PASSWORD_1}".encode("utf-8")
    ).hexdigest()
    return expected.lower() == signature.lower()