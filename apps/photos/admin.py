from django.contrib import admin

from .models import GeneratedResult, Order, OrderReview, PhotoStyle, UploadedPhoto


@admin.register(PhotoStyle)
class PhotoStyleAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "sort_order"]
    prepopulated_fields = {"slug": ("name",)}


class UploadedPhotoInline(admin.TabularInline):
    model = UploadedPhoto
    extra = 0


class GeneratedResultInline(admin.TabularInline):
    model = GeneratedResult
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "style", "status", "user", "anon_id", "created_at"]
    list_filter = ["status", "style"]
    inlines = [UploadedPhotoInline, GeneratedResultInline]


@admin.register(OrderReview)
class OrderReviewAdmin(admin.ModelAdmin):
    list_display = ["order", "rating", "source", "short_comment", "is_public", "created_at"]
    list_editable = ["is_public"]
    list_filter = ["is_public", "rating", "source"]
    search_fields = ["comment", "order__id"]
    raw_id_fields = ["order"]

    @admin.display(description="Комментарий")
    def short_comment(self, obj):
        return obj.comment[:80]
