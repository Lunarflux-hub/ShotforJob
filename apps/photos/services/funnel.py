"""
Логирование этапов /workstation: загрузка → обрезка → отправка → заказ →
генерация → результат показан. Каждый этап — FunnelEvent в БД (отчёт в
админке) и строка в лог сервера (logger "funnel") с user_id и устройством.

Запись этапа никогда не роняет основной поток: аналитика вторична.
"""
from __future__ import annotations

import logging
import re

from ..models import FunnelEvent

logger = logging.getLogger("funnel")

# Этапы, которые может прислать браузер (static/js/funnel.js). Серверные
# (order_created, order_rejected, generation_*) пишутся только кодом сервера.
CLIENT_STAGES = {
    "page_open",        # открыл /workstation
    "photo_selected",   # выбрал/перетащил фото: count, types, sizes_mb
    "photo_rejected",   # не принято на клиенте: reason (too_big, too_many)
    "crop_opened",      # открылось окно обрезки
    "crop_applied",     # нажал «Применить»
    "crop_skipped",     # «Пропустить» или тап мимо окна
    "crop_failed",      # фото не открылось в обрезке / не удалось сохранить: reason
    "submit_clicked",   # нажал «Сгенерировать»
    "submit_blocked",   # форма не отправлена: reason (no_style, no_photos)
    "submit_error",     # сервер ответил ошибкой: status
    "page_hidden",      # свернул вкладку во время генерации
    "page_visible",     # вернулся на вкладку во время генерации
    "result_seen",      # результат показан на странице: order_id, is_free_preview
    "result_failed_seen",  # на странице показана ошибка генерации
}
SERVER_STAGES = {"order_created", "order_rejected", "generation_started", "generation_done", "generation_failed"}

META_MAX_KEYS = 12
META_MAX_STR = 200


def detect_device(user_agent: str) -> str:
    ua = user_agent or ""
    if re.search(r"iPhone|iPad|iPod", ua):
        return FunnelEvent.Device.IOS
    if "Android" in ua:
        return FunnelEvent.Device.ANDROID
    if re.search(r"Windows|Macintosh|X11|Linux", ua):
        return FunnelEvent.Device.DESKTOP
    return FunnelEvent.Device.OTHER


def clean_meta(meta) -> dict:
    """Плоский словарь простых значений — клиент не должен писать в БД что угодно."""
    if not isinstance(meta, dict):
        return {}
    cleaned = {}
    for key, value in list(meta.items())[:META_MAX_KEYS]:
        key = str(key)[:40]
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            cleaned[key] = value
        elif isinstance(value, str):
            cleaned[key] = value[:META_MAX_STR]
        elif isinstance(value, list):
            cleaned[key] = [v if isinstance(v, (int, float, bool)) else str(v)[:60] for v in value[:5]]
    return cleaned


def record(stage: str, *, user=None, order=None, session_id: str = "", user_agent: str = "", meta=None) -> None:
    try:
        user_agent = (user_agent or "")[:300]
        device = detect_device(user_agent) if user_agent else (order.device if order and order.device else "other")
        meta = clean_meta(meta)
        user_id = getattr(user, "id", None) or (order.user_id if order else None)
        FunnelEvent.objects.create(
            stage=stage,
            session_id=(session_id or "")[:64],
            user_id=user_id,
            order=order,
            device=device,
            user_agent=user_agent or (order.user_agent if order else ""),
            meta=meta,
        )
        logger.info(
            "funnel stage=%s user=%s device=%s order=%s session=%s meta=%s",
            stage, user_id, device, getattr(order, "id", None), session_id or "-", meta,
        )
    except Exception:  # noqa: BLE001 — аналитика не должна ломать генерацию и оплату
        logger.exception("Не удалось записать этап воронки %s", stage)
