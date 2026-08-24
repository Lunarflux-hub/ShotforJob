from django.apps import AppConfig


class PhotosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.photos"
    verbose_name = "Фотогенерация"

    def ready(self):
        from . import signals  # noqa: F401
