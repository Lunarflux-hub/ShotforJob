from rest_framework import serializers

from apps.photos.services import storage

from .models import Carousel
from .services.copywriter import CAPTION_MAX

MIN_SLIDES, MAX_SLIDES = 3, 10


class CarouselSerializer(serializers.ModelSerializer):
    # presigned-ссылки считаются заново на каждый запрос (бакет приватный,
    # см. apps/photos/services/storage.py)
    images = serializers.SerializerMethodField()

    class Meta:
        model = Carousel
        fields = [
            "id",
            "topic",
            "slides_count",
            "theme",
            "handle",
            "slides",
            "caption",
            "images",
            "status",
            "error_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_images(self, obj):
        if obj.status != Carousel.Status.DONE:
            return []
        return [storage.generate_presigned_url(key) for key in obj.image_keys]


class CarouselCreateSerializer(serializers.Serializer):
    topic = serializers.CharField(min_length=5, max_length=500)
    slides_count = serializers.IntegerField(min_value=MIN_SLIDES, max_value=MAX_SLIDES, default=7)
    theme = serializers.ChoiceField(choices=Carousel.Theme.choices, default=Carousel.Theme.LIGHT)
    handle = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class SlideSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, allow_blank=True)
    body = serializers.CharField(max_length=1000, allow_blank=True)


class CarouselRerenderSerializer(serializers.Serializer):
    """Правки пользователя: тексты слайдов, тема, подпись. Картинки
    пересобираются без повторного вызова нейросети."""

    slides = SlideSerializer(many=True, min_length=2, max_length=MAX_SLIDES)
    theme = serializers.ChoiceField(choices=Carousel.Theme.choices)
    handle = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    caption = serializers.CharField(max_length=CAPTION_MAX, required=False, allow_blank=True)
