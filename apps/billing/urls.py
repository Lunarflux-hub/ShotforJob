from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("config/", views.BillingConfigView.as_view(), name="config"),
    path("topup/", views.CreateTopupView.as_view(), name="create_topup"),
    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view(), name="payment_detail"),
    path("balance/", views.BalanceView.as_view(), name="balance"),
    path("robokassa/result/", views.robokassa_result, name="robokassa_result"),
    path("robokassa/success/", views.robokassa_success, name="robokassa_success"),
    path("robokassa/fail/", views.robokassa_fail, name="robokassa_fail"),
]
