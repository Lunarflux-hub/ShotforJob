from django.conf import settings
from rest_framework import serializers

from .models import GeneratedResult, Order, PhotoStyle, UploadedPhoto
from .services import storage


class PhotoStyleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PhotoStyle
        fields = ["id", "name", "slug", "description", "preview_image"]


class GeneratedResultSerializer(serializers.ModelSerializer):
    # Пересчитываем presigned URL при каждом запросе, чтобы ссылка на
    # скачивание не протухала даже в старой истории заказов
    # (бакет в Yandex Object Storage приватный, см. services/storage.py).
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedResult
        fields = ["id", "file_url", "created_at"]

    def get_file_url(self, obj):
        return storage.generate_presigned_url(obj.s3_key)


class UploadedPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedPhoto
        fields = ["id", "image", "uploaded_at"]


class OrderSerializer(serializers.ModelSerializer):
    style = PhotoStyleSerializer(read_only=True)
    uploaded_photos = UploadedPhotoSerializer(many=True, read_only=True)
    results = GeneratedResultSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "style",
            "status",
            "error_message",
            "clothing",
            "background_type",
            "background_color",
            "uploaded_photos",
            "results",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OrderCreateSerializer(serializers.Serializer):
    """
    Принимает multipart/form-data:
      style_id: int
      photos: список файлов (1-3 штуки), ключ повторяется: photos, photos, photos

      Необязательные параметры настройки (со страницы /workstation),
      которые подставляются в промпт при генерации:
      clothing: "casual" | "formal" | "sport" | "jacket" | "shirt"
      background_type: "office" | "nature" | "solid" | "upload"
      background_color: hex-цвет, например "#0066FF"
      background_image: файл — своё изображение фона (при background_type="upload")
    """

    style_id = serializers.PrimaryKeyRelatedField(
        queryset=PhotoStyle.objects.filter(is_active=True), source="style"
    )
    photos = serializers.ListField(
        child=serializers.ImageField(), min_length=1, max_length=settings.MAX_UPLOAD_PHOTOS
    )
    clothing = serializers.ChoiceField(
        choices=["casual", "formal", "sport", "jacket", "shirt"],
        required=False,
        allow_blank=True,
    )
    background_type = serializers.ChoiceField(
        choices=["office", "nature", "solid", "upload"],
        required=False,
        allow_blank=True,
    )
    background_color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$", required=False, allow_blank=True
    )
    background_image = serializers.ImageField(required=False, allow_null=True)

    def validate_photos(self, value):
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        for photo in value:
            if photo.size > max_bytes:
                raise serializers.ValidationError(
                    f"Файл {photo.name} превышает {settings.MAX_UPLOAD_SIZE_MB} МБ"
                )
        return value

    def validate_background_image(self, value):
        if value is None:
            return value
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError(
                f"Файл фона превышает {settings.MAX_UPLOAD_SIZE_MB} МБ"
            )
        return value