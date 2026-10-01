(() => {
    const API_BASE = "/api";

    const listEl = document.getElementById("resultsList");
    const emptyEl = document.getElementById("resultsEmpty");
    const errorEl = document.getElementById("resultsError");
    const loadingEl = document.getElementById("resultsLoading");

    const t = (ru, en) => (window.SFJ_t ? window.SFJ_t(ru, en) : ru);
    const unlockMessageEl = document.getElementById("resultsUnlockMessage");

    // Превью открылось с баланса («Скачать в HD · 1 генерация» в unlock.js)
    async function handleUnlocked(orderId, data) {
        if (data.charged && unlockMessageEl) {
            unlockMessageEl.textContent = window.SFJUnlock.balanceText(data.balance);
            unlockMessageEl.classList.remove("d-none");
        }
        window.SFJUnlock.startDownload(data.result.download_url);
        listEl.innerHTML = "";
        await loadHistory();
        showInlineReview(listEl.querySelector(`.order-item[data-order-id="${orderId}"]`));
    }

    const STATUS_LABELS = {
        pending: "в очереди",
        processing: "генерируется",
        done: "готово",
        failed: "ошибка",
    };

    function formatDate(iso) {
        const d = new Date(iso);
        return d.toLocaleString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function renderOrder(order) {
        const li = document.createElement("li");
        li.className = "order-item";

        const latestResult = order.results && order.results[0];
        const thumbHtml = latestResult
            ? `<img src="${latestResult.file_url}" alt="Результат" class="order-thumb">`
            : `<div class="order-thumb order-thumb-placeholder">${STATUS_LABELS[order.status] || order.status}</div>`;

        let actionsHtml;
        if (latestResult && latestResult.is_locked) {
            // Бесплатное превью: оригинал открывается через «Скачать в HD» (unlock.js)
            // Кнопки оплаты в один шаг дорисует unlock.js (см. loadHistory)
            actionsHtml = `
                <span class="preview-badge">${t("Превью со знаком", "Watermarked preview")}</span>
                <div class="js-offers" data-result-id="${latestResult.id}"></div>
            `;
        } else if (latestResult) {
            const reportUrl = `/support/?order_id=${order.id}&result_id=${latestResult.id}`;
            actionsHtml = `
                <a href="${latestResult.download_url || latestResult.file_url}" download class="btn-pill primary">${t("Скачать", "Download")}</a>
                <a href="${reportUrl}" class="btn-link-muted">${t("Сообщить о проблеме", "Report a problem")}</a>
            `;
        } else {
            actionsHtml = `<span class="order-status-text">${STATUS_LABELS[order.status] || order.status}</span>`;
        }

        li.dataset.orderId = order.id;
        li.dataset.hasReview = order.review ? "1" : "";
        li.innerHTML = `
            ${thumbHtml}
            <div class="order-info">
                <div class="order-style">${order.style ? order.style.name : "—"}</div>
                <div class="order-date">${formatDate(order.created_at)}</div>
            </div>
            <div class="order-actions">${actionsHtml}</div>
        `;
        return li;
    }

    // ---------- Оценка после скачивания HD ----------
    // Под заказом без отзыва после скачивания появляется строка «Оцените фото»:
    // звёзды + необязательный комментарий → POST /api/orders/<id>/review/
    // (дальше — модерация в админке, на главную попадают только одобренные).
    function showInlineReview(li) {
        if (!li || li.dataset.hasReview || li.nextElementSibling?.classList.contains("inline-review")) return;
        const box = document.createElement("li");
        box.className = "inline-review";
        const title = document.createElement("span");
        title.className = "inline-review-title";
        title.textContent = t("Оцените фото:", "Rate the photo:");
        const stars = document.createElement("span");
        stars.className = "inline-review-stars";
        stars.setAttribute("role", "radiogroup");
        let rating = 0;
        const comment = document.createElement("input");
        comment.className = "inline-review-comment";
        comment.maxLength = 2000;
        comment.placeholder = t("Пара слов (необязательно)", "A few words (optional)");
        const send = document.createElement("button");
        send.type = "button";
        send.className = "btn-pill primary";
        send.textContent = t("Отправить", "Send");
        send.disabled = true;
        for (let n = 1; n <= 5; n++) {
            const star = document.createElement("button");
            star.type = "button";
            star.textContent = "★";
            star.setAttribute("aria-label", `${n} / 5`);
            star.addEventListener("click", () => {
                rating = n;
                stars.querySelectorAll("button").forEach((b, i) => b.classList.toggle("active", i < n));
                send.disabled = false;
            });
            stars.appendChild(star);
        }
        send.addEventListener("click", async () => {
            send.disabled = true;
            const doFetch = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
            try {
                const resp = await doFetch(`${API_BASE}/orders/${li.dataset.orderId}/review/`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ rating, comment: comment.value.trim() }),
                });
                if (!resp.ok) throw new Error();
                li.dataset.hasReview = "1";
                box.replaceChildren(Object.assign(document.createElement("span"), {
                    className: "inline-review-title",
                    textContent: t("Спасибо за отзыв! 💙", "Thanks for your review! 💙"),
                }));
            } catch (e) {
                send.disabled = false;
                send.textContent = t("Не отправилось — ещё раз", "Failed — try again");
            }
        });
        box.append(title, stars, comment, send);
        li.after(box);
    }

    listEl.addEventListener("click", (e) => {
        const link = e.target.closest("a[download]");
        if (link) showInlineReview(link.closest(".order-item"));
    });

    async function loadHistory() {
        try {
            const doFetch = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
            const resp = await doFetch(`${API_BASE}/orders/history/`);
            if (!resp.ok) throw new Error("Не удалось загрузить историю заказов");
            const orders = await resp.json();

            loadingEl.classList.add("d-none");

            if (!orders.length) {
                emptyEl.classList.remove("d-none");
                return;
            }

            orders.forEach((order) => listEl.appendChild(renderOrder(order)));
            listEl.classList.remove("d-none");
            listEl.querySelectorAll(".js-offers").forEach((box) => {
                const orderId = box.closest(".order-item").dataset.orderId;
                window.SFJUnlock.renderLockedActions(box, Number(box.dataset.resultId), {
                    onUnlocked: (data) => handleUnlocked(orderId, data),
                });
            });
            // «Ещё 5 вариантов в другом стиле» — только уже платившим (upsell.js)
            if (orders.some((o) => o.results && o.results.length) && window.SFJUpsell) {
                window.SFJUpsell.show(document.getElementById("upsellCard"));
            }
        } catch (e) {
            loadingEl.classList.add("d-none");
            errorEl.textContent = e.message;
            errorEl.classList.remove("d-none");
        }
    }

    document.addEventListener("DOMContentLoaded", loadHistory);
})();