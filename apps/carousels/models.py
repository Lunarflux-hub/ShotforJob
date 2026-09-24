import uuid

from django.conf import settings
from django.db import models


class Carousel(models.Model):
    """
    Карусель для Instagram: нейросеть пишет тексты слайдов по теме
    пользователя (services/copywriter.py), затем слайды рисуются в PNG
    1080×1350 или 1080×1080 (services/renderer.py) и кладутся в S3. Пользователь может
    поправить тексты и пересобрать картинки без повторного вызова нейросети.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        PROCESSING = "processing", "Генерируется"
        DONE = "done", "Готово"
        FAILED = "failed", "Ошибка"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="carousels")

    topic = models.TextField(help_text="О чём карусель — формулировка пользователя")
    slides_count = models.PositiveSmallIntegerField(default=7)
    # Пресет цветов — ключ из services/renderer.THEMES
    theme = models.CharField(max_length=20, default="light")
    # Остальное оформление (акцент, выравнивание, узор, формат…) —
    # см. services/renderer.DEFAULT_DESIGN
    design = models.JSONField(default=dict, blank=True)
    # Подпись в углу каждого слайда, например @username
    handle = models.CharField(max_length=40, blank=True)

    # [{"layout", "emoji", "title", "body", "items", "value"}, ...] —
    # см. services/renderer.py; после генерации первый слайд обложка, последний призыв
    slides = models.JSONField(default=list, blank=True)
    # Подпись к посту (текст под каруселью + хэштеги) — пишет та же нейросеть
    caption = models.TextField(blank=True)
    # S3-ключи отрисованных слайдов в том же порядке, что и slides
    image_keys = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]
        verbose_name = "Карусель"
        verbose_name_plural = "Карусели"

    def __str__(self):
        return f"Карусель «{self.topic[:40]}» ({self.status})"
