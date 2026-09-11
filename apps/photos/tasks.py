import logging
from datetime import timedelta
from email.mime.image import MIMEImage

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from .models import GeneratedResult, Order
from .services import storage
from .services.polza_client import PolzaClientError, generate_image_from_reference
from .services.prompt_builder import build_prompt

logger = logging.getLogger(__name__)

RESULT_PHOTO_CID = "result_photo"


@shared_task
def generate_photo_task(order_id: str):
    """
    Основной пайплайн:
    1. Забираем заказ и загруженные фото.
    2. Собираем промпт из шаблона стиля.
    3. Отправляем запрос в Polza.ai.
    4. Скачиваем результат и кладём в Yandex Object Storage.
    5. Обновляем статус заказа.
    """
    try:
        order = Order.objects.select_related("style").get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order %s не найден", order_id)
        return

    order.status = Order.Status.PROCESSING
    order.save(update_fields=["status", "updated_at"])

    photos = list(order.uploaded_photos.all())
    if not photos:
        order.status = Order.Status.FAILED
        order.error_message = "Нет загруженных фото для генерации"
        order.save(update_fields=["status", "error_message", "updated_at"])
        return

    prompt = build_prompt(order)

    try:
        reference_paths = [p.image.path for p in photos]
        # Если пользователь загрузил своё изображение фона — добавляем его
        # последним в список референсов; build_prompt() уже включил в промпт
        # инструкцию использовать это изображение только как фон, а не как
        # источник лица.
        if order.background_image:
            reference_paths.append(order.background_image.path)

        result = generate_image_from_reference(prompt=prompt, reference_image_paths=reference_paths)

        if result.image_url:
            s3_key, public_url = storage.upload_from_url(result.image_url, str(order.id))
        elif result.image_bytes:
            s3_key, public_url = storage.upload_generated_bytes(result.image_bytes, str(order.id))
        else:
            raise PolzaClientError("Polza.ai не вернул ни image_url, ни image_bytes в ответе")

        result = GeneratedResult.objects.create(order=order, s3_key=s3_key, file_url=public_url)

        order.status = Order.Status.DONE
        order.error_message = ""
        order.save(update_fields=["status", "error_message", "updated_at"])

        if order.user_id and order.user.email:
            send_order_result_email.delay(result.id)

    except PolzaClientError as exc:
        logger.warning("Ошибка Polza.ai для заказа %s: %s", order_id, exc)
        order.status = Order.Status.FAILED
        order.error_message = str(exc)
        order.save(update_fields=["status", "error_message", "updated_at"])

    except Exception as exc:  # noqa: BLE001
        logger.exception("Неожиданная ошибка генерации для заказа %s", order_id)
        order.status = Order.Status.FAILED
        order.error_message = f"Внутренняя ошибка: {exc}"
        order.save(update_fields=["status", "error_message", "updated_at"])


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_order_result_email(self, result_id: int):
    """
    Отправляет пользователю на почту готовое фото (см. generate_photo_task
    выше — ставится в очередь сразу после того, как заказ переходит в DONE,
    и только если у заказа есть авторизованный пользователь с email —
    анонимным заказам письмо отправлять некуда).

    Как и в apps.support.tasks.send_support_ticket_email, фото скачивается и
    вшивается в письмо как inline-вложение (cid), а presigned-ссылка на
    оригинал остаётся запасным вариантом на случай, если клиент блокирует
    встроенные картинки.
    """
    try:
        result = GeneratedResult.objects.select_related("order__user").get(id=result_id)
    except GeneratedResult.DoesNotExist:
        logger.error("GeneratedResult %s не найден", result_id)
        return

    order = result.order
    if not order.user_id or not order.user.email:
        logger.info("У заказа %s нет пользователя с email — фото не отправляем", order.id)
        return

    photo_url = storage.generate_presigned_url(result.s3_key)
    try:
        photo_bytes = storage.download_bytes(result.s3_key)
    except Exception:
        # Не критично: письмо всё равно уйдёт, просто со ссылкой вместо
        # вшитой картинки — не хотим ронять всю отправку из-за этого
        logger.exception("Не удалось скачать фото %s для вложения в письмо", result.s3_key)
        photo_bytes = None

    context = {
        "order": order,
        "photo_url": photo_url,
        "photo_cid": RESULT_PHOTO_CID if photo_bytes else None,
    }
    html_body = render_to_string("emails/order_result_email.html", context)
    text_body = strip_tags(html_body) + f"\n\nСкачать фото: {photo_url}"

    try:
        mail = EmailMultiAlternatives(
            subject="Ваше фото готово — ShotForJob",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email],
        )
        mail.attach_alternative(html_body, "text/html")

        if photo_bytes:
            mail.mixed_subtype = "related"
            image = MIMEImage(photo_bytes, _subtype="png")
            image.add_header("Content-ID", f"<{RESULT_PHOTO_CID}>")
            image.add_header("Content-Disposition", "inline", filename="photo.png")
            mail.attach(image)

        mail.send(fail_silently=False)
        logger.info("Фото по заказу %s отправлено на %s", order.id, order.user.email)

    except Exception as exc:  # noqa: BLE001 — любая ошибка почтового провайдера должна попадать в retry/лог
        logger.exception("Не удалось отправить фото по заказу %s", order.id)
        raise self.retry(exc=exc)


@shared_task
def cleanup_expired_uploads():
    """
    Удаляет исходные фото пользователей (media/uploads/...) с диска и из БД.

    Фото нужны только на время генерации (шлём их в Polza.ai как референс),
    результат уже лежит отдельно в Yandex Object Storage — хранить исходники
    бесконечно смысла нет, это и лишний риск приватности, и лишнее место на
    диске. При этом удаляем не сразу после генерации, а по истечении
    UPLOAD_RETENTION_HOURS: кнопка «Попробовать снова» переиспользует те же
    файлы без повторной загрузки, и заказ должен успеть побыть в финальном
    статусе достаточно долго, чтобы retry успел сработать.

    Трогаем только заказы в финальном статусе (done/failed) — файлы
    активных/ожидающих генераций (pending/processing) не удаляются.
    """
    cutoff = timezone.now() - timedelta(hours=settings.UPLOAD_RETENTION_HOURS)

    expired_orders = Order.objects.filter(
        status__in=[Order.Status.DONE, Order.Status.FAILED],
        updated_at__lt=cutoff,
    ).exclude(uploaded_photos__isnull=True, background_image="")

    photos_deleted = 0
    backgrounds_deleted = 0

    for order in expired_orders.iterator():
        for photo in order.uploaded_photos.all():
            if photo.image:
                photo.image.delete(save=False)
            photo.delete()
            photos_deleted += 1

        if order.background_image:
            order.background_image.delete(save=False)
            order.background_image = None
            order.save(update_fields=["background_image"])
            backgrounds_deleted += 1

    if photos_deleted or backgrounds_deleted:
        logger.info(
            "cleanup_expired_uploads: удалено %s фото и %s фонов старше %s ч.",
            photos_deleted,
            backgrounds_deleted,
            settings.UPLOAD_RETENTION_HOURS,
        )