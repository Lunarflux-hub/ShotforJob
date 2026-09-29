"""
Отчёт по продажам для админки (Платежи → «Отчёт по продажам»).
Считаются только реальные оплаты: status=paid и is_test=False (тестовый
режим, сотрудники и суммы < 10 ₽ помечаются автоматически, см.
services.is_test_payment и миграцию 0015).
"""
from __future__ import annotations

import datetime
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Min
from django.utils import timezone

from .models import Payment


@dataclass
class Row:
    label: str
    revenue: Decimal = Decimal("0")
    payments: int = 0
    buyers: set = field(default_factory=set)
    repeat_payments: int = 0

    @property
    def buyers_count(self) -> int:
        return len(self.buyers)

    @property
    def avg_check(self) -> Decimal:
        return (self.revenue / self.payments).quantize(Decimal("1")) if self.payments else Decimal("0")

    @property
    def repeat_share(self) -> int:
        """Доля повторных покупок, % — платёж считается повторным, если у
        покупателя уже была реальная оплата раньше (в том числе до периода)."""
        return round(self.repeat_payments * 100 / self.payments) if self.payments else 0

    def add(self, payment: Payment, is_repeat: bool) -> None:
        self.revenue += payment.amount
        self.payments += 1
        self.buyers.add(payment.user_id)
        self.repeat_payments += int(is_repeat)


def source_label(payment: Payment) -> str:
    if payment.utm_source:
        medium = f" / {payment.utm_medium}" if payment.utm_medium else ""
        return f"{payment.utm_source}{medium}"
    if payment.yclid:
        return "Яндекс Директ (yclid)"
    return "(без меток)"


def real_payments():
    return Payment.objects.filter(status=Payment.Status.PAID, is_test=False, paid_at__isnull=False)


def sales_report(date_from: datetime.date, date_to: datetime.date) -> dict:
    tz = timezone.get_current_timezone()
    start = datetime.datetime.combine(date_from, datetime.time.min, tzinfo=tz)
    end = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz)

    payments = list(
        real_payments().filter(paid_at__gte=start, paid_at__lt=end).select_related("package").order_by("paid_at")
    )
    # Первая реальная оплата каждого покупателя — за всё время, не только в периоде
    first_paid = dict(
        real_payments()
        .filter(user_id__in={p.user_id for p in payments})
        .values_list("user_id")
        .annotate(first=Min("paid_at"))
    )

    days: "OrderedDict[datetime.date, Row]" = OrderedDict()
    day = date_from
    while day <= date_to:
        days[day] = Row(label=day.strftime("%d.%m.%Y"))
        day += datetime.timedelta(days=1)

    total = Row(label="Итого")
    by_package: dict[str, Row] = defaultdict(lambda: Row(label=""))
    by_source: dict[str, Row] = defaultdict(lambda: Row(label=""))

    for p in payments:
        is_repeat = p.paid_at > first_paid[p.user_id]
        local_day = timezone.localtime(p.paid_at, tz).date()
        days[local_day].add(p, is_repeat)
        total.add(p, is_repeat)
        package = p.package.title if p.package else "—"
        by_package[package].label = package
        by_package[package].add(p, is_repeat)
        source = source_label(p)
        by_source[source].label = source
        by_source[source].add(p, is_repeat)

    sort = lambda rows: sorted(rows.values(), key=lambda r: r.revenue, reverse=True)  # noqa: E731
    return {
        "days": list(reversed(days.values())),  # свежие дни сверху
        "total": total,
        "by_package": sort(by_package),
        "by_source": sort(by_source),
    }
