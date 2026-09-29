(() => {
    const API_BASE = "/api";

    const listEl = document.getElementById("resultsList");
    const emptyEl = document.getElementById("resultsEmpty");
    const errorEl = document.getElementById("resultsError");
    const loadingEl = document.getElementById("resultsLoading");

    const t = (ru, en) => (window.SFJ_t ? window.SFJ_t(ru, en) : ru);
    const unlockMessageEl = document.getElementById("resultsUnlockMessage");

    // «Скачать в HD» у бесплатного превью — делегирование, т.к. список рендерится динамически
    listEl.addEventListener("click", async (e) => {
        const btn = e.target.closest(".js-unlock");
        if (!btn) return;
        btn.disabled = true;
        try {
            const data = await window.SFJUnlock.unlock(btn.dataset.resultId);
            if (!data) return; // ушли на оплату
            if (data.charged && unlockMessageEl) {
                unlockMessageEl.textContent = window.SFJUnlock.balanceText(data.balance);
                unlockMessageEl.classList.remove("d-none");
            }
            window.SFJUnlock.startDownload(data.result.download_url);
            listEl.innerHTML = "";
            loadHistory();
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.classList.remove("d-none");
            btn.disabled = false;
        }
    });

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
            actionsHtml = `
                <span class="preview-badge">${t("Превью со знаком", "Watermarked preview")}</span>
                <button type="button" class="btn-pill primary js-unlock" data-result-id="${latestResult.id}">${t("Скачать в HD", "Download in HD")}</button>
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