"""
Рассылка письма с промокодом.

    # посмотреть, кому уйдёт (ничего не отправляет):
    python manage.py send_promo_email RETURN --all
    # тестовое письмо на один адрес:
    python manage.py send_promo_email RETURN --to me@example.com --send
    # боевая рассылка всем активным пользователям с email:
    python manage.py send_promo_email RETURN --all --send

Без --send команда только печатает список получателей. Отправка идёт
синхронно с паузой между письмами — чтобы не упереться в rate limit
почтового провайдера (Resend).
"""
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from apps.billing.models import PromoCode

SEND_DELAY_SECONDS = 0.6


class Command(BaseCommand):
    help = "Разослать письмо с промокодом (по умолчанию — dry-run, для отправки нужен --send)"

    def add_arguments(self, parser):
        parser.add_argument("code", help="Код промокода, например RETURN")
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument("--to", nargs="+", metavar="EMAIL", help="Отправить только на эти адреса")
        target.add_argument("--all", action="store_true", help="Всем активным пользователям с email")
        parser.add_argument("--send", action="store_true", help="Действительно отправить (иначе dry-run)")

    def handle(self, *args, code, to, all, send, **options):
        promo = PromoCode.objects.filter(code__iexact=code).first()
        if promo is None:
            raise CommandError(f"Промокод {code} не найден")
        if not promo.is_active or promo.valid_until <= timezone.now():
            raise CommandError(f"Промокод {promo.code} неактивен или истёк ({promo.valid_until:%d.%m.%Y})")

        if to:
            recipients = list(dict.fromkeys(email.strip().lower() for email in to))
        else:
            recipients = list(
                get_user_model()
                .objects.filter(is_active=True)
                .exclude(email="")
                .order_by("id")
                .values_list("email", flat=True)
                .distinct()
            )

        discount = (
            f"{promo.discount_value.normalize():f}%"
            if promo.discount_type == PromoCode.DiscountType.PERCENT
            else f"{promo.discount_value.normalize():f} ₽"
        )
        context = {"promo": promo, "discount": discount, "site_url": settings.FRONTEND_URL}
        html_body = render_to_string("emails/promo_email.html", context)
        text_body = strip_tags(html_body)
        subject = f"Скидка {discount} на фото — промокод {promo.code}"

        self.stdout.write(f"Промокод {promo.code}: {discount}, до {promo.valid_until:%d.%m.%Y %H:%M}")
        self.stdout.write(f"Получателей: {len(recipients)}")
        if not send:
            for email in recipients:
                self.stdout.write(f"  {email}")
            self.stdout.write(self.style.WARNING("Dry-run: ничего не отправлено. Добавьте --send."))
            return

        sent, failed = 0, []
        for email in recipients:
            mail = EmailMultiAlternatives(
                subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[email]
            )
            mail.attach_alternative(html_body, "text/html")
            try:
                mail.send(fail_silently=False)
                sent += 1
                self.stdout.write(f"  ✓ {email}")
            except Exception as exc:  # noqa: BLE001 — одна ошибка не должна обрывать всю рассылку
                failed.append(email)
                self.stderr.write(f"  ✗ {email}: {exc}")
            time.sleep(SEND_DELAY_SECONDS)

        self.stdout.write(self.style.SUCCESS(f"Отправлено: {sent}, ошибок: {len(failed)}"))
