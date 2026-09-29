from django.conf import settings
from django.db import models

ATTRIBUTION_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "yclid")


class UserAcquisition(models.Model):
    """
    Откуда пришёл пользователь — UTM-метки и yclid (клик Яндекс Директа) на
    момент регистрации. Метки ловит JS в base.html и кладёт в cookie
    sfj_attr; при первом входе через Google/Яндекс ID они переносятся сюда
    (apps/accounts/attribution.py), а оттуда — в каждый Payment, чтобы в
    отчёте по продажам была видна выручка по источникам.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="acquisition")
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=200, blank=True)
    utm_content = models.CharField(max_length=200, blank=True)
    utm_term = models.CharField(max_length=200, blank=True)
    yclid = models.CharField(max_length=100, blank=True)
    referrer = models.CharField(max_length=500, blank=True)
    landing_page = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Источник регистрации"
        verbose_name_plural = "Источники регистраций"

    def __str__(self):
        return f"{self.user} ← {self.utm_source or 'без меток'}"
