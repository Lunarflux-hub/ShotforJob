from django.urls import path

from .views import (
    FreePreviewStatusView,
    OrderCreateView,
    OrderDetailView,
    OrderListView,
    OrderReviewView,
    PhotoStyleListView,
    ResultUnlockView,
)

urlpatterns = [
    path("styles/", PhotoStyleListView.as_view(), name="style-list"),
    path("orders/", OrderCreateView.as_view(), name="order-create"),
    path("orders/history/", OrderListView.as_view(), name="order-history"),
    path("orders/free-preview/", FreePreviewStatusView.as_view(), name="free-preview-status"),
    path("results/<int:id>/unlock/", ResultUnlockView.as_view(), name="result-unlock"),
    path("orders/<uuid:id>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:id>/review/", OrderReviewView.as_view(), name="order-review"),
]
