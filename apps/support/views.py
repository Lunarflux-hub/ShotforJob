from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.photos.models import Order
from apps.photos.views import OrderOwnershipMixin

from .models import SupportTicket
from .serializers import SupportTicketCreateSerializer, SupportTicketSerializer
from .tasks import send_support_ticket_email


def _get_client_ip(request) -> str | None:
    # За прокси/nginx реальный IP приходит в X-Forwarded-For
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class SupportTicketCreateView(OrderOwnershipMixin, APIView):
    """
    POST /api/support/
    Принимает JSON или form-data: { "email": str, "message": str, "result_id"?: int }.

    1. Валидирует данные (формат email, длина сообщения).
    2. Если передан result_id — проверяет, что это фото принадлежит
       обратившемуся (тот же user/anon_id, что и у заказа с этим результатом),
       иначе 400. Так нельзя приложить к обращению чужое фото.
    3. Сохраняет обращение в support_tickets.
    4. Асинхронно (Celery -> Redis) отправляет письмо в поддержку.
    5. Возвращает { success: true, message: "..." }.

    Защита от спама: ScopedRateThrottle ограничивает число обращений
    с одного IP (см. REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["support"]
    в config/settings.py). Плюс глобальный AnonRateThrottle/UserRateThrottle
    уже настроены на проекте.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "support"

    def post(self, request):
        serializer = SupportTicketCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        related_result = serializer.validated_data.get("related_result")
        if related_result is not None:
            owner_filter = self.get_owner_filter(request)
            belongs_to_requester = Order.objects.filter(
                owner_filter, id=related_result.order_id
            ).exists()
            if not belongs_to_requester:
                return Response(
                    {"success": False, "errors": {"result_id": ["Фото не найдено"]}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        ticket = serializer.save(ip_address=_get_client_ip(request))

        # Ставим задачу в очередь Redis (Celery) — сам ответ пользователю
        # не блокируется отправкой письма
        send_support_ticket_email.delay(str(ticket.id))

        return Response(
            {
                "success": True,
                "message": "Спасибо, мы ответим вам в ближайшее время",
                "ticket": SupportTicketSerializer(ticket).data,
            },
            status=status.HTTP_201_CREATED,
        )
