import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import GeneratedResult, Order
from .services import storage
from .services.polza_client import PolzaClientError, generate_image_from_reference
from .services.prompt_builder import build_prompt

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def generate_photo_task(self, order_id: str):
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

        GeneratedResult.objects.create(order=order, s3_key=s3_key, file_url=public_url)

        order.status = Order.Status.DONE
        order.error_message = ""
        order.save(update_fields=["status", "error_message", "updated_at"])

    except PolzaClientError as exc:
        logger.warning("Ошибка Polza.ai для заказа %s: %s", order_id, exc)
        order.status = Order.Status.FAILED
        order.error_message = str(exc)
        order.save(update_fields=["status", "error_message", "updated_at"])
        # Пробуем повторить (на случай временного сбоя апи)
        raise self.retry(exc=exc)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Неожиданная ошибка генерации для заказа %s", order_id)
        order.status = Order.Status.FAILED
        order.error_message = f"Внутренняя ошибка: {exc}"
        order.save(update_fields=["status", "error_message", "updated_at"])


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