import uuid

from django.conf import settings
from django.db import models


def uploaded_photo_path(instance, filename):
    return f"uploads/{instance.order_id}/{filename}"


def background_image_path(instance, filename):
    return f"uploads/{instance.id}/background_{filename}"


class PhotoStyle(models.Model):
    """
    Стиль/тип генерации: «Для паспорта», «Деловое портфолио», «Креативное» и т.д.
    prompt_template — базовый промпт (общий стиль, освещение, качество).
    Детали, которые пользователь настраивает на /workstation (одежда, фон/
    локация, цвет фона, своё фоновое изображение), в промпт НЕ зашиваются
    здесь — они автоматически добавляются поверх этого шаблона в
    services/prompt_builder.py::build_prompt().
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    prompt_template = models.TextField(
        help_text="Промпт, отправляемый в Polza.ai для этого стиля"
    )
    preview_image = models.ImageField(upload_to="style_previews/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        PROCESSING = "processing", "Генерируется"
        DONE = "done", "Готово"
        FAILED = "failed", "Ошибка"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Пользователь может быть не авторизован — тогда заказ привязывается
    # к анонимному идентификатору (см. apps.photos.utils.get_or_create_anon_id)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
        null=True,
        blank=True,
    )
    anon_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    style = models.ForeignKey(PhotoStyle, on_delete=models.PROTECT, related_name="orders")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)

    # ---- Параметры настройки из /workstation, которые подставляются в промпт ----
    # Одежда: casual/formal/sport (обычные стили) или jacket/shirt (документные)
    clothing = models.CharField(max_length=20, blank=True)
    # Тип фона/окружения: office/nature/solid/upload. Пусто — фон берётся из
    # style.prompt_template как есть (например, для документных стилей, где
    # выбор фона сводится только к цвету).
    background_type = models.CharField(max_length=20, blank=True)
    # Цвет фона в hex (для background_type="solid" либо для документных стилей,
    # где выбор фона всегда однотонный).
    background_color = models.CharField(max_length=7, blank=True)
    # Своё изображение фона (для background_type="upload") — используется как
    # доп. референс при генерации.
    background_image = models.ImageField(
        upload_to=background_image_path, blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["anon_id", "-created_at"]),
        ]

    def __str__(self):
        return f"Order {self.id} ({self.status})"


class UploadedPhoto(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="uploaded_photos")
    image = models.ImageField(upload_to=uploaded_photo_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"UploadedPhoto для {self.order_id}"


class GeneratedResult(models.Model):
    """
    Результат генерации. Одна заявка может содержать несколько попыток
    («Попробовать снова» создаёт новую запись, а не перезаписывает старую —
    так пользователь может сравнить варианты).
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="results")
    s3_key = models.CharField(max_length=500)
    file_url = models.URLField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Result для {self.order_id}"
