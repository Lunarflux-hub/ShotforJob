from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from .models import GenerationPackage, Payment, GenerationLedgerEntry
from .payanyway import build_payment_request, verify_pay_url_signature
from .serializers import PaymentSerializer
from . import services


class PollingAnonRateThrottle(AnonRateThrottle):
    scope = "polling"


class PollingUserRateThrottle(UserRateThrottle):
    scope = "polling"


class BillingConfigView(APIView):
    """GET /api/billing/config/ — список пакетов генераций, доступных для покупки."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        has_paid_before = bool(
            user and Payment.objects.filter(user=user, status=Payment.Status.PAID).exists()
        )

        packages = []
        for p in GenerationPackage.objects.filter(is_active=True):
            promo_active = p.first_purchase_price is not None and not has_paid_before
            packages.append(
                {
                    "id": p.id,
                    "title": p.title,
                    "price": str(p.price),
                    "generations": p.generations,
                    "promo_price": str(p.first_purchase_price) if promo_active else None,
                }
            )
        return Response({"packages": packages})


class CreateTopupView(APIView):
    """
    POST /api/billing/topup/ — создаёт платёж за выбранный пакет генераций и
    возвращает данные для отправки формы на PayAnyWay (MONETA.Assistant).
    Купить можно только готовый пакет — свободная сумма не поддерживается.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        package_id = request.data.get("package_id")
        if not package_id:
            return Response({"error": "package_id_required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            package = GenerationPackage.objects.get(id=package_id, is_active=True)
        except GenerationPackage.DoesNotExist:
            return Response({"error": "invalid_package"}, status=status.HTTP_400_BAD_REQUEST)

        amount = package.price
        is_promo = False
        if package.first_purchase_price is not None:
            already_paid = Payment.objects.filter(
                user=request.user, status=Payment.Status.PAID
            ).exists()
            if not already_paid:
                amount = package.first_purchase_price
                is_promo = True

        payment = Payment.objects.create(
            user=request.user,
            package=package,
            amount=amount,
            generations_granted=package.generations,
            is_test=settings.PAYANYWAY_TEST_MODE,
        )

        promo_suffix = " (акция: первая генерация)" if is_promo else ""
        description = f"Пакет «{package.title}»{promo_suffix} — {package.generations} генераций"
        req = build_payment_request(payment, description, email=request.user.email)

        return Response(
            {
                "payment_id": payment.id,
                "action_url": req["action_url"],
                "method": req["method"],
                "fields": req["fields"],
            }
        )


class PaymentDetailView(APIView):
    """GET /api/billing/payments/<id>/ — статус одного платежа (для страницы чека)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            payment = Payment.objects.get(id=pk, user=request.user)
        except Payment.DoesNotExist:
            return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentSerializer(payment).data)


class PaymentListView(generics.ListAPIView):
    """GET /api/billing/payments/ — история всех платежей текущего пользователя."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by("-created_at")


class BalanceView(APIView):
    """GET /api/billing/balance/ — текущий баланс генераций пользователя."""

    permission_classes = [permissions.IsAuthenticated]
    # Виджет баланса дергается и в шапке, и в форме, на каждой странице —
    # не должен делить общий "user"-лимит с остальным API.
    throttle_classes = [PollingAnonRateThrottle, PollingUserRateThrottle]

    def get(self, request):
        return Response({"balance": services.get_balance(request.user)})


@csrf_exempt
def payanyway_result(request):
    """Server-to-server "Pay URL" callback от системы Moneta.ru (PayAnyWay).
    Единственное место начисления генераций. Параметры могут прийти методом
    GET или POST в зависимости от настроек расширенного счёта — принимаем оба.
    Отвечаем текстом SUCCESS/FAIL с заголовком 200 OK, как требует документация
    PayAnyWay (в т.ч. на пустой проверочный запрос при сохранении URL в ЛК)."""
    if request.method not in ("GET", "POST"):
        return HttpResponse("FAIL", status=200)

    data = request.GET if request.method == "GET" else request.POST

    # Пустой проверочный запрос при сохранении Pay URL в личном кабинете Moneta.ru —
    # параметров нет, но ответ 200 OK всё равно обязателен.
    if not data:
        return HttpResponse("SUCCESS", status=200)

    mnt_transaction_id = data.get("MNT_TRANSACTION_ID", "")
    mnt_operation_id = data.get("MNT_OPERATION_ID", "")
    mnt_amount = data.get("MNT_AMOUNT", "")
    mnt_currency_code = data.get("MNT_CURRENCY_CODE", "")
    mnt_subscriber_id = data.get("MNT_SUBSCRIBER_ID", "")
    mnt_test_mode = data.get("MNT_TEST_MODE", "")
    signature = data.get("MNT_SIGNATURE", "")

    if not verify_pay_url_signature(
        mnt_transaction_id, mnt_operation_id, mnt_amount,
        mnt_currency_code, mnt_subscriber_id, mnt_test_mode, signature,
    ):
        return HttpResponse("FAIL", status=200)

    try:
        payment_id = int(mnt_transaction_id)
    except ValueError:
        return HttpResponse("FAIL", status=200)

    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().get(id=payment_id)
        except Payment.DoesNotExist:
            return HttpResponse("FAIL", status=200)

        # Идемпотентность — если уже оплачен, просто возвращаем SUCCESS
        if payment.status == Payment.Status.PAID:
            return HttpResponse("SUCCESS", status=200)

        # Сверяем сумму
        if Decimal(mnt_amount) != payment.amount:
            return HttpResponse("FAIL", status=200)

        payment.status = Payment.Status.PAID
        payment.paid_at = timezone.now()
        payment.payanyway_operation_id = mnt_operation_id
        payment.raw_result_payload = dict(data)
        payment.save(update_fields=["status", "paid_at", "payanyway_operation_id", "raw_result_payload"])

        services.credit_generations(
            payment.user,
            payment.generations_granted,
            kind=GenerationLedgerEntry.Kind.TOPUP,
            payment=payment,
        )

    return HttpResponse("SUCCESS", status=200)


def payanyway_success(request):
    """Редирект пользователя на фронт (Success URL). НЕ начисляет генерации."""
    data = request.GET if request.method == "GET" else request.POST
    inv_id = data.get("MNT_TRANSACTION_ID", "")
    return redirect(f"{settings.FRONTEND_URL}/billing/success?invoice={inv_id}")


def payanyway_fail(request):
    """Fail URL — пользователь отменил оплату или она не прошла."""
    data = request.GET if request.method == "GET" else request.POST
    inv_id = data.get("MNT_TRANSACTION_ID", "")
    return redirect(f"{settings.FRONTEND_URL}/billing/fail?invoice={inv_id}")