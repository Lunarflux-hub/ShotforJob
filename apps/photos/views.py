from django.db import transaction
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.billing.services import InsufficientBalanceError, spend_generation

from .models import Order, PhotoStyle, UploadedPhoto
from .serializers import OrderCreateSerializer, OrderSerializer, PhotoStyleSerializer
from .tasks import generate_photo_task
from .utils import ANON_ID_COOKIE, ANON_ID_MAX_AGE, get_or_create_anon_id


class PollingAnonRateThrottle(AnonRateThrottle):
    scope = "polling"


class PollingUserRateThrottle(UserRateThrottle):
    scope = "polling"


class PhotoStyleListView(generics.ListAPIView):
    """GET /api/styles/ — список доступных стилей для лендинга/шага выбора."""

    queryset = PhotoStyle.objects.filter(is_active=True)
    serializer_class = PhotoStyleSerializer


class OrderOwnershipMixin:
    """
    Общая логика поиска заказов: авторизованный пользователь видит свои заказы
    по user_id, анонимный — по anon_id из cookie.
    """

    def get_owner_filter(self, request):
        if request.user and request.user.is_authenticated:
            return Q(user=request.user)
        anon_id, _ = get_or_create_anon_id(request)
        return Q(anon_id=anon_id)


class OrderCreateView(OrderOwnershipMixin, APIView):
    """
    POST /api/orders/
    multipart/form-data: style_id, photos (1-3 файла)
    Требует авторизации и баланса ≥ 1 генерации: списывает 1 генерацию
    атомарно, затем создаёт заказ и ставит задачу генерации в очередь Celery.
    Если генерация в итоге упадёт с ошибкой — списанная генерация НЕ
    возвращается (продуктовое решение), заказ уйдёт в статус failed.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    user=request.user,
                    style=serializer.validated_data["style"],
                    status=Order.Status.PENDING,
                    clothing=serializer.validated_data.get("clothing", ""),
                    background_type=serializer.validated_data.get("background_type", ""),
                    background_color=serializer.validated_data.get("background_color", ""),
                    background_image=serializer.validated_data.get("background_image"),
                )
                # Списываем генерацию тут же, в той же транзакции: если баланса
                # не хватит, InsufficientBalanceError откатит и создание order.
                spend_generation(request.user, order=order)

                for photo in serializer.validated_data["photos"]:
                    UploadedPhoto.objects.create(order=order, image=photo)
        except InsufficientBalanceError as exc:
            return Response(
                {
                    "error": "insufficient_balance",
                    "detail": "Недостаточно генераций на балансе. Пополните баланс.",
                    "balance": exc.balance,
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        generate_photo_task.delay(str(order.id))

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(OrderOwnershipMixin, generics.RetrieveAPIView):
    """GET /api/orders/{id}/ — статус и результат заказа (для поллинга с фронта)."""

    serializer_class = OrderSerializer
    lookup_field = "id"
    # Свой (щедрый) лимит: этот эндпоинт дергается каждые 3с во время генерации
    # и не должен делить общий "user"-лимит с созданием заказов.
    throttle_classes = [PollingAnonRateThrottle, PollingUserRateThrottle]

    def get_queryset(self):
        return Order.objects.filter(self.get_owner_filter(self.request))


class OrderRetryView(OrderOwnershipMixin, APIView):
    """
    POST /api/orders/{id}/retry/
    «Попробовать снова» — перезапускает генерацию с теми же фото и стилем,
    не заставляя пользователя перезагружать фото. Генерация уже была списана
    при создании заказа и повторно не списывается — retry использует ту же
    оплаченную попытку.
    """

    def post(self, request, id):
        order = Order.objects.filter(self.get_owner_filter(request), id=id).first()
        if not order:
            return Response({"detail": "Заказ не найден"}, status=status.HTTP_404_NOT_FOUND)

        order.status = Order.Status.PENDING
        order.error_message = ""
        order.save(update_fields=["status", "error_message", "updated_at"])

        generate_photo_task.delay(str(order.id))
        return Response(OrderSerializer(order).data)


class OrderListView(OrderOwnershipMixin, generics.ListAPIView):
    """GET /api/orders/ — история заказов текущего пользователя (для ЛК)."""

    serializer_class = OrderSerializer
    throttle_classes = [PollingAnonRateThrottle, PollingUserRateThrottle]

    def get_queryset(self):
        return Order.objects.filter(self.get_owner_filter(self.request))

