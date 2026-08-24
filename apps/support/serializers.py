from django.utils.html import strip_tags
from rest_framework import serializers

from apps.photos.models import GeneratedResult

from .models import SupportTicket


class SupportTicketCreateSerializer(serializers.ModelSerializer):
    """
    Принимает JSON или form-data: { "email": "...", "message": "...", "result_id": 123 }.
    email — стандартная валидация EmailField (проверяет формат).
    message — минимум 10 символов (без учёта пробелов по краям).
    result_id — опционально: id конкретного сгенерированного фото (GeneratedResult),
    если обращение касается конкретной генерации. Проверка, что фото
    действительно принадлежит обратившемуся, происходит во view
    (там доступен request для определения владельца).
    """

    result_id = serializers.PrimaryKeyRelatedField(
        source="related_result",
        queryset=GeneratedResult.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = SupportTicket
        fields = ["email", "message", "result_id"]

    def validate_message(self, value):
        # На всякий случай вырезаем HTML-теги — обращение не должно
        # содержать разметку (защита от XSS при показе в админке/письме)
        cleaned = strip_tags(value).strip()
        if len(cleaned) < 10:
            raise serializers.ValidationError(
                "Сообщение должно содержать минимум 10 символов"
            )
        return cleaned

    def validate_email(self, value):
        return value.strip().lower()


class SupportTicketSerializer(serializers.ModelSerializer):
    """Используется только для ответа после успешного создания обращения."""

    class Meta:
        model = SupportTicket
        fields = ["id", "email", "message", "related_result", "status", "created_at"]
        read_only_fields = fields
