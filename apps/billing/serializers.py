from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    package_title = serializers.CharField(source="package.title", default="", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

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
        ]
