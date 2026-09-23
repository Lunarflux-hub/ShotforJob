from django.urls import path

from .views import (
    CarouselAccessView,
    CarouselDetailView,
    CarouselDownloadView,
    CarouselListCreateView,
    CarouselRerenderView,
)

urlpatterns = [
    path("access/", CarouselAccessView.as_view(), name="carousel-access"),
    path("", CarouselListCreateView.as_view(), name="carousel-list"),
    path("<uuid:id>/", CarouselDetailView.as_view(), name="carousel-detail"),
    path("<uuid:id>/rerender/", CarouselRerenderView.as_view(), name="carousel-rerender"),
    path("<uuid:id>/download/", CarouselDownloadView.as_view(), name="carousel-download"),
]
