"""
Бета-доступ к каруселям: пока фича в тесте, она видна только аккаунтам из
settings.CAROUSEL_BETA_EMAILS. Для всех остальных API отвечает 404 — как
будто раздела не существует.
"""
from django.conf import settings
from django.http import Http404
from rest_framework.permissions import BasePermission


def has_carousel_access(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and user.email
        and user.email.lower() in settings.CAROUSEL_BETA_EMAILS
    )


class CarouselBetaAccess(BasePermission):
    def has_permission(self, request, view):
        if not has_carousel_access(request.user):
            raise Http404
        return True
