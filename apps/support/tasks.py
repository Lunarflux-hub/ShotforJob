import logging
from email.mime.image import MIMEImage

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from apps.photos.services import storage

from .models import SupportTicket

logger = logging.getLogger(__name__)

SUPPORT_PHOTO_CID = "support_photo"


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_support_ticket_email(self, ticket_id: str):
    """
    Забирает обращение из БД и отправляет письмо на SUPPORT_EMAIL через SMTP
    (настройки берутся из EMAIL_* переменных окружения, см. config/settings.py).

    Если к обращению приложено конкретное фото (ticket.related_result):
    - presigned-ссылка на него генерируется заново прямо здесь, в момент
      отправки — а не была сохранена при создании тикета — чтобы не протухла
      к моменту, когда воркер реально отправит письмо;
    - само фото скачивается и вшивается в письмо как inline-вложение (cid),
      а не просто ссылкой — так оно точно отобразится в теле письма, даже
      если почтовый клиент блокирует загрузку внешних картинок. Presigned
      URL всё равно остаётся в письме как запасной вариант и для скачивания
      в оригинальном качестве.

    Задача идемпотентна к повторному вызову: при неудаче Celery делает
    до 3 повторных попыток с задержкой 30 секунд (сеть/SMTP могут быть
    временно недоступны).
    """
    try:
        ticket = SupportTicket.objects.select_related("related_result").get(id=ticket_id)
    except SupportTicket.DoesNotExist:
        logger.error("Обращение %s не найдено", ticket_id)
        return

    subject = f"Новое обращение от {ticket.email}"

    photo_url = None
    photo_bytes = None
    if ticket.related_result_id:
        photo_url = storage.generate_presigned_url(ticket.related_result.s3_key)
        try:
            photo_bytes = storage.download_bytes(ticket.related_result.s3_key)
        except Exception:
            # Не критично: письмо всё равно уйдёт, просто со ссылкой вместо
            # вшитой картинки — не хотим ронять всю отправку из-за этого
            logger.exception(
                "Не удалось скачать фото %s для вложения в письмо",
                ticket.related_result.s3_key,
            )

    context = {
        "email": ticket.email,
        "message": ticket.message,
        "ticket_id": str(ticket.id),
        "created_at": ticket.created_at,
        "photo_url": photo_url,
        "photo_cid": SUPPORT_PHOTO_CID if photo_bytes else None,
    }

    html_body = render_to_string("emails/support_ticket_email.html", context)
    text_body = strip_tags(html_body)
    if photo_url:
        text_body += f"\n\nФото, к которому относится обращение: {photo_url}"

    try:
        mail = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.SUPPORT_EMAIL],
            reply_to=[ticket.email],  # чтобы ответить прямо пользователю
        )
        mail.attach_alternative(html_body, "text/html")

        if photo_bytes:
            # multipart/related нужен, чтобы почтовые клиенты корректно
            # показывали инлайн-картинку внутри HTML-версии, а не как
            # отдельный файл-вложение
            mail.mixed_subtype = "related"
            image = MIMEImage(photo_bytes, _subtype="png")
            image.add_header("Content-ID", f"<{SUPPORT_PHOTO_CID}>")
            image.add_header("Content-Disposition", "inline", filename="photo.png")
            mail.attach(image)

        mail.send(fail_silently=False)

        ticket.status = SupportTicket.Status.SENT
        ticket.error_message = ""
        ticket.save(update_fields=["status", "error_message", "updated_at"])
        logger.info("Письмо по обращению %s отправлено", ticket_id)

    except Exception as exc:  # noqa: BLE001 — любая ошибка SMTP должна попадать в retry/лог
        logger.exception("Не удалось отправить письмо по обращению %s", ticket_id)
        ticket.status = SupportTicket.Status.FAILED
        ticket.error_message = str(exc)
        ticket.save(update_fields=["status", "error_message", "updated_at"])
        raise self.retry(exc=exc)
