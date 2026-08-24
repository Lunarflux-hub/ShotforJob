from decimal import Decimal, ROUND_DOWN

MIN_TOPUP = Decimal("100")
MAX_TOPUP = Decimal("100000")
BASE_RATE = Decimal("10")  # 1 кредит = 10 руб. при базовой цене


def credits_for_amount(amount: Decimal) -> int:
    """Курс с бонусом за объём – пример прогрессивной формулы."""
    if amount >= 10000:
        rate = BASE_RATE * Decimal("0.85")   # +15% кредитов
    elif amount >= 3000:
        rate = BASE_RATE * Decimal("0.92")
    else:
        rate = BASE_RATE
    return int((amount / rate).to_integral_value(rounding=ROUND_DOWN))


def get_formula_params() -> dict:
    """Возвращает параметры формулы для фронта (live-превью)."""
    return {
        "base_rate": float(BASE_RATE),
        "tiers": [
            {"threshold": 3000, "multiplier": 0.92},
            {"threshold": 10000, "multiplier": 0.85},
        ],
    }