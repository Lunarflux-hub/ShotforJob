from django.conf import settings
from django.db import models


class SocialAccount(models.Model):
    """
    Связь локального пользователя с аккаунтом во внешнем провайдере.
    Ключ поиска — (provider, provider_user_id), а не email: у Yandex ID
    email может быть не передан пользователем, а у Google встречаются
    случаи смены email на аккаунте — id провайдера при этом не меняется.
    """

    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"
        YANDEX = "yandex", "Yandex ID"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_accounts"
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_user_id = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("provider", "provider_user_id")

    def __str__(self):
        return f"{self.provider}:{self.provider_user_id} -> {self.user}"
