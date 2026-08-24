from django.contrib import admin

from .models import GeneratedResult, Order, PhotoStyle, UploadedPhoto


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
