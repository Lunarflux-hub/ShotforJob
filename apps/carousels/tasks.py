import logging
import uuid

from celery import shared_task

from apps.photos.services import storage

from .models import Carousel
from .services.copywriter import CopywriterError, write_carousel
from .services.renderer import render_carousel

logger = logging.getLogger(__name__)


def _render_and_upload(carousel: Carousel) -> None:
    images = render_carousel(carousel.slides, carousel.theme, carousel.handle)
    # Новый префикс на каждую пересборку: старые presigned-ссылки в открытой
    # вкладке не начнут внезапно показывать другую картинку.
    batch = uuid.uuid4().hex[:8]
    keys = []
    for i, data in enumerate(images, start=1):
        key = f"carousels/{carousel.id}/{batch}/{i:02d}.png"
        storage.upload_bytes(data, key, content_type="image/png")
        keys.append(key)
    carousel.image_keys = keys


def _fail(carousel: Carousel, message: str) -> None:
    carousel.status = Carousel.Status.FAILED
    carousel.error_message = message
    carousel.save(update_fields=["status", "error_message", "updated_at"])


@shared_task
def generate_carousel_task(carousel_id: str, *, rewrite: bool = True):
    """
    rewrite=True — нейросеть пишет тексты заново (новая карусель);
    rewrite=False — только перерисовать слайды из carousel.slides (после
    правок пользователя или смены темы), без вызова нейросети.
    """
    try:
        carousel = Carousel.objects.get(id=carousel_id)
    except Carousel.DoesNotExist:
        logger.error("Carousel %s не найдена", carousel_id)
        return

    carousel.status = Carousel.Status.PROCESSING
    carousel.error_message = ""
    carousel.save(update_fields=["status", "error_message", "updated_at"])

    try:
        if rewrite:
            carousel.slides, carousel.caption = write_carousel(carousel.topic, carousel.slides_count)
        _render_and_upload(carousel)
    except CopywriterError as exc:
        logger.warning("Ошибка генерации текста для карусели %s: %s", carousel_id, exc)
        _fail(carousel, str(exc))
        return
    except Exception:  # noqa: BLE001
        logger.exception("Неожиданная ошибка генерации карусели %s", carousel_id)
        _fail(carousel, "Внутренняя ошибка, попробуйте ещё раз")
        return

    carousel.status = Carousel.Status.DONE
    carousel.save(update_fields=["slides", "caption", "image_keys", "status", "updated_at"])
