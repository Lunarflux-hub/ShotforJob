import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Payment

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_payment_receipt_email(self, payment_id: int):
    """
    Отправляет пользователю чек об оплате после успешного платежа
    (см. apps.billing.views.payanyway_result — единственное место,
    ставящее эту задачу в очередь). Асинхронно через Celery — сам
    server-to-server callback от PayAnyWay не должен ждать почтового
    провайдера.
    """
    try:
        payment = Payment.objects.select_related("user", "package", "promo_code").get(id=payment_id)
    except Payment.DoesNotExist:
        logger.error("Payment %s не найден", payment_id)
        return

    if not payment.user.email:
        logger.info("У пользователя %s нет email — чек не отправляем", payment.user_id)
        return

    context = {"payment": payment}
    html_body = render_to_string("emails/payment_receipt_email.html", context)
    text_body = strip_tags(html_body)

    try:
        mail = EmailMultiAlternatives(
            subject=f"Чек об оплате №{payment.id} — ShotForJob",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[payment.user.email],
        )
        mail.attach_alternative(html_body, "text/html")
        mail.send(fail_silently=False)
        logger.info("Чек по платежу %s отправлен на %s", payment_id, payment.user.email)

    except Exception as exc:  # noqa: BLE001 — любая ошибка почтового провайдера должна попадать в retry/лог
        logger.exception("Не удалось отправить чек по платежу %s", payment_id)
        raise self.retry(exc=exc)
