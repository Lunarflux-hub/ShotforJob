from django.db import transaction
from django.db.models import Q
from django.views.generic import TemplateView
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.billing import catalog, services
from apps.billing.services import InsufficientBalanceError, spend_generation

from .models import GeneratedResult, Order, PhotoStyle, UploadedPhoto
from .serializers import (
    GeneratedResultSerializer,
    OrderCreateSerializer,
    OrderReviewSerializer,
    OrderSerializer,
    PhotoStyleSerializer,
)
from .services import free_preview
from .services.reviews import landing_reviews, save_review
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
        ip = free_preview.client_ip(request)

        try:
            with transaction.atomic():
                # Лочим баланс первым делом: под этой блокировкой решаем
                # «списать / бесплатное превью / 402», чтобы параллельные
                # запросы не получили два бесплатных превью.
                balance = services.lock_balance(request.user)
                is_free = False
                if balance.generations < 1:
                    reason = free_preview.eligibility(request.user, ip)
                    if reason is not None:
                        raise InsufficientBalanceError(balance.generations, 1)
                    is_free = True

                order = Order.objects.create(
                    user=request.user,
                    style=serializer.validated_data["style"],
                    status=Order.Status.PENDING,
                    clothing=serializer.validated_data.get("clothing", ""),
                    background_type=serializer.validated_data.get("background_type", ""),
                    background_color=serializer.validated_data.get("background_color", ""),
                    background_image=serializer.validated_data.get("background_image"),
                    is_free_preview=is_free,
                    client_ip=ip,
                )
                if not is_free:
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


class FreePreviewStatusView(APIView):
    """GET /api/orders/free-preview/ — положено ли бесплатное превью (для
    подсказки на /workstation и кнопки «Попробовать бесплатно»)."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [PollingAnonRateThrottle, PollingUserRateThrottle]

    def get(self, request):
        balance = services.get_balance(request.user)
        reason = free_preview.eligibility(request.user, free_preview.client_ip(request))
        return Response({"eligible": balance < 1 and reason is None, "balance": balance})


class ResultUnlockView(APIView):
    """
    POST /api/results/{id}/unlock/ — «Скачать в HD» для бесплатного превью.
    Есть генерации — списывает 1 и отдаёт ссылку на оригинал; нет — 402 со
    ссылкой на оплату «Оптимального», после которой вебхук разблокирует фото
    сам (Payment.unlock_result). Уже открытый результат — просто ссылка.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        result = GeneratedResult.objects.filter(id=id, order__user=request.user).first()
        if result is None:
            return Response({"detail": "Фото не найдено"}, status=status.HTTP_404_NOT_FOUND)

        try:
            charged = free_preview.unlock(result, request.user)
        except InsufficientBalanceError:
            return Response(
                {
                    "error": "insufficient_balance",
                    "pay_url": f"/payment/?package=optimal&unlock={result.id}",
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        result.refresh_from_db()
        return Response(
            {
                "charged": charged,
                "balance": services.get_balance(request.user),
                "result": GeneratedResultSerializer(result).data,
            }
        )


class OrderDetailView(OrderOwnershipMixin, generics.RetrieveAPIView):
    """GET /api/orders/{id}/ — статус и результат заказа (для поллинга с фронта)."""

    serializer_class = OrderSerializer
    lookup_field = "id"
    # Свой (щедрый) лимит: этот эндпоинт дергается каждые 3с во время генерации
    # и не должен делить общий "user"-лимит с созданием заказов.
    throttle_classes = [PollingAnonRateThrottle, PollingUserRateThrottle]

    def get_queryset(self):
        return Order.objects.filter(self.get_owner_filter(self.request))


class OrderListView(OrderOwnershipMixin, generics.ListAPIView):
    """GET /api/orders/ — история заказов текущего пользователя (для ЛК)."""

    serializer_class = OrderSerializer
    throttle_classes = [PollingAnonRateThrottle, PollingUserRateThrottle]

    def get_queryset(self):
        return Order.objects.filter(self.get_owner_filter(self.request)).select_related("review")



class OrderReviewView(OrderOwnershipMixin, APIView):
    """
    POST /api/orders/{id}/review/ — { "rating": 1..5, "comment"?: str }.
    Отзыв о готовой генерации; повторный POST перезаписывает прошлый отзыв.
    """

    def post(self, request, id):
        order = (
            Order.objects.filter(self.get_owner_filter(request), id=id, status=Order.Status.DONE)
            .first()
        )
        if order is None:
            return Response({"detail": "Заказ не найден"}, status=status.HTTP_404_NOT_FOUND)

        serializer = OrderReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = save_review(
            order,
            rating=serializer.validated_data["rating"],
            comment=serializer.validated_data.get("comment", ""),
            source="web",
        )
        return Response(OrderReviewSerializer(review).data, status=status.HTTP_200_OK)


class LandingView(TemplateView):
    """Главная страница: к контексту добавлены отзывы для карусели."""

    template_name = "index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tariffs"] = catalog.public_tariffs()
        context["min_price_per_photo"] = catalog.min_price_per_photo()
        context["min_package_price"] = catalog.min_package_price()
        context["reviews"] = landing_reviews()
        # ~8с на карточку — скорость ленты не зависит от числа отзывов
        context["reviews_duration"] = len(context["reviews"]) * 8
        return context
