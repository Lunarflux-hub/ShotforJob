from rest_framework import serializers

from apps.photos.services import storage

from .models import Carousel
from .services.copywriter import CAPTION_MAX
from .services.renderer import DEFAULT_DESIGN, HEIGHTS, LAYOUTS, PATTERNS, THEMES, TITLE_SCALES

MIN_SLIDES, MAX_SLIDES = 3, 10
MAX_EDITED_SLIDES = 20  # в редакторе можно добавить блоков больше, чем генерирует нейросеть (Instagram: до 20)
THEME_CHOICES = list(THEMES)


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
            "design",
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


class DesignSerializer(serializers.Serializer):
    accent = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", required=False, allow_blank=True)
    align = serializers.ChoiceField(choices=["left", "center"], required=False)
    pattern = serializers.ChoiceField(choices=PATTERNS, required=False)
    aspect = serializers.ChoiceField(choices=list(HEIGHTS), required=False)
    title_scale = serializers.ChoiceField(choices=list(TITLE_SCALES), required=False)
    show_numbers = serializers.BooleanField(required=False)
    show_counter = serializers.BooleanField(required=False)
    show_swipe = serializers.BooleanField(required=False)

    def to_internal_value(self, data):
        return {**DEFAULT_DESIGN, **super().to_internal_value(data)}


class CarouselCreateSerializer(serializers.Serializer):
    topic = serializers.CharField(min_length=5, max_length=500)
    slides_count = serializers.IntegerField(min_value=MIN_SLIDES, max_value=MAX_SLIDES, default=7)
    theme = serializers.ChoiceField(choices=THEME_CHOICES, default="light")
    design = DesignSerializer(required=False, default=dict)
    handle = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class SlideSerializer(serializers.Serializer):
    layout = serializers.ChoiceField(choices=LAYOUTS)
    emoji = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    body = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    items = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=True), required=False, default=list, max_length=10
    )
    value = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class CarouselRerenderSerializer(serializers.Serializer):
    """Правки пользователя: блоки-слайды, тема и оформление, подпись.
    Картинки пересобираются без повторного вызова нейросети."""

    slides = SlideSerializer(many=True, min_length=1, max_length=MAX_EDITED_SLIDES)
    theme = serializers.ChoiceField(choices=THEME_CHOICES)
    design = DesignSerializer(required=False, default=dict)
    handle = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    caption = serializers.CharField(max_length=CAPTION_MAX, required=False, allow_blank=True)


class SlidePreviewSerializer(serializers.Serializer):
    """Один блок для живого превью в редакторе (ничего не сохраняет)."""

    slide = SlideSerializer()
    index = serializers.IntegerField(min_value=0, max_value=MAX_EDITED_SLIDES - 1)
    total = serializers.IntegerField(min_value=1, max_value=MAX_EDITED_SLIDES)
    # Номер пункта с учётом остальных блоков (редактор считает сам, см. slide_numbers)
    number = serializers.IntegerField(min_value=0, max_value=MAX_EDITED_SLIDES, required=False)
    theme = serializers.ChoiceField(choices=THEME_CHOICES)
    design = DesignSerializer(required=False, default=dict)
    handle = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
