from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("config/", views.BillingConfigView.as_view(), name="config"),
    path("topup/", views.CreateTopupView.as_view(), name="create_topup"),
    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view(), name="payment_detail"),
    path("balance/", views.BalanceView.as_view(), name="balance"),
    path("payanyway/result/", views.payanyway_result, name="payanyway_result"),
    path("payanyway/success/", views.payanyway_success, name="payanyway_success"),
    path("payanyway/fail/", views.payanyway_fail, name="payanyway_fail"),
]
