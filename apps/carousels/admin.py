from django.contrib import admin

from .models import Carousel


@admin.register(Carousel)
class CarouselAdmin(admin.ModelAdmin):
    list_display = ["short_topic", "user", "theme", "slides_count", "status", "created_at"]
    list_filter = ["status", "theme"]
    search_fields = ["topic", "user__email"]
    raw_id_fields = ["user"]

    @admin.display(description="Тема")
    def short_topic(self, obj):
        return obj.topic[:60]
