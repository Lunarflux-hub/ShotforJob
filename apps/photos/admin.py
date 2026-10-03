import datetime

from django.contrib import admin
from django.db.models import Count
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone

from .models import FunnelEvent, GeneratedResult, Order, OrderReview, PhotoStyle, UploadedPhoto


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
    fields = ["s3_key", "is_free_preview", "unlocked", "unlocked_at", "preview_s3_key", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "style", "status", "is_free_preview", "device", "user", "client_ip", "created_at"]
    list_filter = ["status", "is_free_preview", "device", "style"]
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


# Порядок шагов в отчёте — путь человека по /workstation
FUNNEL_STEPS = [
    ("page_open", "Открыл /workstation"),
    ("photo_selected", "Выбрал фото"),
    ("crop_opened", "Открылась обрезка"),
    ("crop_applied", "Применил обрезку"),
    ("crop_skipped", "Пропустил обрезку"),
    ("crop_failed", "Обрезка не удалась"),
    ("submit_clicked", "Нажал «Сгенерировать»"),
    ("submit_blocked", "Форма не отправлена (проверка)"),
    ("submit_error", "Сервер вернул ошибку"),
    ("order_created", "Заказ создан"),
    ("generation_done", "Генерация готова"),
    ("generation_failed", "Генерация упала"),
    ("page_hidden", "Свернул во время генерации"),
    ("result_seen", "Увидел результат на странице"),
]
DEVICES = [("android", "Android"), ("ios", "iOS"), ("desktop", "Десктоп"), ("other", "Другое")]


@admin.register(FunnelEvent)
class FunnelEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "stage", "device", "user", "order", "session_id", "meta"]
    list_filter = ["stage", "device", "created_at"]
    search_fields = ["session_id", "user__email", "order__id"]
    raw_id_fields = ["user", "order"]
    change_list_template = "admin/photos/funnelevent/change_list.html"

    def get_urls(self):
        return [
            path("report/", self.admin_site.admin_view(self.report_view), name="photos_funnel_report"),
        ] + super().get_urls()

    def report_view(self, request):
        """Сколько разных браузеров (session_id; для серверных этапов — заказов)
        дошло до каждого шага, по устройствам."""
        today = timezone.localdate()
        try:
            date_from = datetime.date.fromisoformat(request.GET.get("from") or (today - datetime.timedelta(days=6)).isoformat())
            date_to = datetime.date.fromisoformat(request.GET.get("to") or today.isoformat())
        except ValueError:
            date_from, date_to = today - datetime.timedelta(days=6), today
        tz = timezone.get_current_timezone()
        start = datetime.datetime.combine(date_from, datetime.time.min, tzinfo=tz)
        end = datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz)
        events = FunnelEvent.objects.filter(created_at__gte=start, created_at__lt=end)

        # Клиентские этапы считаем по браузерам, серверные — по заказам/пользователям
        counts = {}
        for row in (
            events.exclude(session_id="").values("stage", "device").annotate(n=Count("session_id", distinct=True))
        ):
            counts[(row["stage"], row["device"])] = row["n"]
        for row in events.filter(session_id="").values("stage", "device").annotate(n=Count("order", distinct=True)):
            counts[(row["stage"], row["device"])] = counts.get((row["stage"], row["device"]), 0) + row["n"]

        rows = []
        for stage, label in FUNNEL_STEPS:
            values = [counts.get((stage, d), 0) for d, _ in DEVICES]
            rows.append({"stage": stage, "label": label, "values": values, "total": sum(values)})
        reasons = (
            events.filter(stage__in=["crop_failed", "submit_blocked", "submit_error", "order_rejected", "generation_failed"])
            .values("stage", "device", "meta")
        )
        reason_counts = {}
        for r in reasons:
            meta = r["meta"] or {}
            key = (r["stage"], r["device"], str(meta.get("reason") or meta.get("status") or meta.get("kind") or meta.get("error") or "—")[:80])
            reason_counts[key] = reason_counts.get(key, 0) + 1

        context = {
            **self.admin_site.each_context(request),
            "title": "Воронка /workstation",
            "opts": self.model._meta,
            "date_from": date_from,
            "date_to": date_to,
            "devices": [label for _, label in DEVICES],
            "rows": rows,
            "reasons": sorted(reason_counts.items(), key=lambda kv: -kv[1]),
        }
        return TemplateResponse(request, "admin/photos/funnel_report.html", context)
