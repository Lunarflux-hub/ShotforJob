from django.urls import path

from .views import OrderCreateView, OrderDetailView, OrderListView, OrderRetryView, PhotoStyleListView

urlpatterns = [
    path("styles/", PhotoStyleListView.as_view(), name="style-list"),
    path("orders/", OrderCreateView.as_view(), name="order-create"),
    path("orders/history/", OrderListView.as_view(), name="order-history"),
    path("orders/<uuid:id>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:id>/retry/", OrderRetryView.as_view(), name="order-retry"),
]
