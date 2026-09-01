"""
Диагностика ошибки "Неправильная подпись формы оплаты" в PayAnyWay.

Запуск:
    python manage.py payanyway_debug
    python manage.py payanyway_debug --amount 199.00 --transaction-id 42

Печатает:
  - какие значения реально загружены из .env (MNT_ID виден полностью,
    код проверки целостности — только длина и первые/последние символы,
    чтобы не светить секрет в логах, но чтобы вы могли заметить случайный
    пробел/перенос строки),
  - строку, которая идёт в md5() для подписи формы оплаты,
  - итоговую MNT_SIGNATURE.

Сверьте эту подпись с той, что получится, если выполнить php-код из
документации PayAnyWay (раздел "Формирование платежной кнопки через
MONETA.Assistant") с ТЕМИ ЖЕ значениями MNT_ID/MNT_TRANSACTION_ID/
MNT_AMOUNT/MNT_CURRENCY_CODE/MNT_TEST_MODE и кодом проверки целостности
из личного кабинета Moneta.ru. Если суммы совпадают, а Moneta всё равно
ругается — проблема на 99% в личном кабинете: не совпадает код проверки
целостности, либо не включена опция "Подпись формы оплаты обязательна",
либо MNT_ID указывает не на тот счёт.
"""
import hashlib

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Диагностика подписи PayAnyWay (MONETA.Assistant)"

    def add_arguments(self, parser):
        parser.add_argument("--transaction-id", default="1")
        parser.add_argument("--amount", default="12.00")

    def handle(self, *args, **options):
        mnt_id = str(settings.PAYANYWAY_MNT_ID or "").strip()
        code = str(settings.PAYANYWAY_INTEGRITY_CODE or "").strip()
        currency = str(settings.PAYANYWAY_CURRENCY_CODE or "").strip()
        test_mode = "1" if settings.PAYANYWAY_TEST_MODE else "0"

        self.stdout.write(self.style.MIGRATE_HEADING("Текущая конфигурация PayAnyWay:"))
        self.stdout.write(f"  PAYANYWAY_MNT_ID           = {mnt_id!r}")
        if not mnt_id:
            self.stdout.write(self.style.ERROR("    -> ПУСТО! MNT_ID не задан в .env"))

        if code:
            masked = f"{code[:2]}...{code[-2:]} (длина {len(code)})" if len(code) > 4 else "***"
            self.stdout.write(f"  PAYANYWAY_INTEGRITY_CODE   = {masked}")
        else:
            self.stdout.write(self.style.ERROR("  PAYANYWAY_INTEGRITY_CODE   = ПУСТО!"))

        self.stdout.write(f"  PAYANYWAY_CURRENCY_CODE    = {currency!r}")
        self.stdout.write(f"  PAYANYWAY_TEST_MODE        = {settings.PAYANYWAY_TEST_MODE!r} -> MNT_TEST_MODE={test_mode!r}")

        mnt_transaction_id = str(options["transaction_id"])
        mnt_amount = f'{float(options["amount"]):.2f}'

        raw = mnt_id + mnt_transaction_id + mnt_amount + currency + test_mode + code
        signature = hashlib.md5(raw.encode("utf-8")).hexdigest()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Тестовый расчёт подписи:"))
        self.stdout.write(f"  MNT_ID              = {mnt_id}")
        self.stdout.write(f"  MNT_TRANSACTION_ID  = {mnt_transaction_id}")
        self.stdout.write(f"  MNT_AMOUNT          = {mnt_amount}")
        self.stdout.write(f"  MNT_CURRENCY_CODE   = {currency}")
        self.stdout.write(f"  MNT_TEST_MODE       = {test_mode}")
        self.stdout.write(f"  строка для md5()    = {mnt_id}{mnt_transaction_id}{mnt_amount}{currency}{test_mode}{'*' * len(code) if code else '<КОД ПУСТ>'}")
        self.stdout.write(self.style.SUCCESS(f"  MNT_SIGNATURE       = {signature}"))
        self.stdout.write("")
        self.stdout.write(
            "Проверьте: выполните php-код из документации PayAnyWay "
            "(http://sandbox.onlinephpfunctions.com) с этими же MNT_ID/"
            "MNT_TRANSACTION_ID/MNT_AMOUNT/MNT_CURRENCY_CODE/MNT_TEST_MODE "
            "и реальным кодом проверки целостности из ЛК Moneta.ru. "
            "Если полученная там подпись совпадает с MNT_SIGNATURE выше — "
            "код в .env верный, и проблема в настройках расширенного счёта "
            "(опция 'Подпись формы оплаты обязательна' должна быть 'Да', "
            "'Тип интерфейса' — 'MONETA.Assistant')."
        )
