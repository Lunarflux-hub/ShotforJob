import io
import zipfile

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.photos.services import storage
from apps.photos.views import PollingAnonRateThrottle, PollingUserRateThrottle

from .access import CarouselBetaAccess, has_carousel_access
from .models import Carousel
from .serializers import CarouselCreateSerializer, CarouselRerenderSerializer, CarouselSerializer
from .services.copywriter import normalize_slides
from .tasks import generate_carousel_task

BETA_PERMISSIONS = [permissions.IsAuthenticated, CarouselBetaAccess]


class CarouselAccessView(APIView):
    """GET /api/carousels/access/ — показывать ли пункт меню «Карусели».
    Всегда 200, чтобы фронт не шумел ошибками у обычных пользователей."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [PollingAnonRateThrottle, PollingUserRateThrottle]

    def get(self, request):
        return Response({"enabled": has_carousel_access(request.user)})


class CarouselListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/carousels/ — карусели пользователя.
    POST /api/carousels/ — { topic, slides_count?, theme?, handle? }: создаёт
    карусель и ставит генерацию (текст + картинки) в очередь Celery.
    """

    permission_classes = BETA_PERMISSIONS
    serializer_class = CarouselSerializer

    def get_queryset(self):
        return Carousel.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = CarouselCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        carousel = Carousel.objects.create(user=request.user, **serializer.validated_data)
        generate_carousel_task.delay(str(carousel.id))
        return Response(CarouselSerializer(carousel).data, status=status.HTTP_201_CREATED)


class CarouselDetailView(generics.RetrieveAPIView):
    """GET /api/carousels/{id}/ — статус и слайды (фронт поллит во время генерации)."""

    permission_classes = BETA_PERMISSIONS
    serializer_class = CarouselSerializer
    lookup_field = "id"
    throttle_classes = [PollingAnonRateThrottle, PollingUserRateThrottle]

    def get_queryset(self):
        return Carousel.objects.filter(user=self.request.user)


class CarouselRerenderView(APIView):
    """POST /api/carousels/{id}/rerender/ — сохранить правки текстов/темы и
    перерисовать слайды без повторного вызова нейросети."""

    permission_classes = BETA_PERMISSIONS

    def post(self, request, id):
        carousel = get_object_or_404(Carousel, id=id, user=request.user)
        if carousel.status in (Carousel.Status.PENDING, Carousel.Status.PROCESSING):
            return Response(
                {"detail": "Карусель ещё генерируется, подождите"}, status=status.HTTP_409_CONFLICT
            )

        serializer = CarouselRerenderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        carousel.slides = normalize_slides(data["slides"])
        carousel.slides_count = len(carousel.slides)
        carousel.theme = data["theme"]
        carousel.handle = data.get("handle", "")
        if "caption" in data:
            carousel.caption = data["caption"]
        carousel.status = Carousel.Status.PENDING
        carousel.save()

        generate_carousel_task.delay(str(carousel.id), rewrite=False)
        return Response(CarouselSerializer(carousel).data)


class CarouselDownloadView(APIView):
    """GET /api/carousels/{id}/download/ — ZIP со слайдами (01.png…) и
    подписью к посту (caption.txt)."""

    permission_classes = BETA_PERMISSIONS

    def get(self, request, id):
        carousel = get_object_or_404(Carousel, id=id, user=request.user, status=Carousel.Status.DONE)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:  # PNG уже сжат
            for i, key in enumerate(carousel.image_keys, start=1):
                archive.writestr(f"{i:02d}.png", storage.download_bytes(key))
            if carousel.caption:
                archive.writestr("caption.txt", carousel.caption)

        response = HttpResponse(buffer.getvalue(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="carousel-{str(carousel.id)[:8]}.zip"'
        return response
