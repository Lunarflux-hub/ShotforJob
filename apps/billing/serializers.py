from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    package_title = serializers.CharField(source="package.title", default="", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    # Оплата из «Скачать в HD»: открылось ли фото (для сообщения на странице чека)
    unlock_done = serializers.SerializerMethodField()

    def get_unlock_done(self, obj):
        return bool(obj.unlock_result_id and obj.unlock_result and obj.unlock_result.unlocked)

    class Meta:
        model = Payment
        fields = [
            "id",
            "amount",
            "currency",
            "generations_granted",
            "status",
            "status_display",
            "package_title",
            "created_at",
            "paid_at",
            "unlock_result_id",
            "unlock_done",
        ]
