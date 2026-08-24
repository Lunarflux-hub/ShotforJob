(() => {
    const API_BASE = "/api";

    const listEl = document.getElementById("resultsList");
    const emptyEl = document.getElementById("resultsEmpty");
    const errorEl = document.getElementById("resultsError");
    const loadingEl = document.getElementById("resultsLoading");

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
        if (latestResult) {
            const reportUrl = `/support/?order_id=${order.id}&result_id=${latestResult.id}`;
            actionsHtml = `
                <a href="${latestResult.file_url}" download class="btn-pill primary">Скачать</a>
                <a href="${reportUrl}" class="btn-link-muted">Сообщить о проблеме</a>
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
        } catch (e) {
            loadingEl.classList.add("d-none");
            errorEl.textContent = e.message;
            errorEl.classList.remove("d-none");
        }
    }

    document.addEventListener("DOMContentLoaded", loadHistory);
})();