/**
 * Логика страницы /billing/history/ — список всех платежей пользователя.
 * Зависит от window.PhotoStudioAuth (auth.js).
 */
(() => {
    const API_BASE = "/api/billing";

    const listEl = document.getElementById("historyList");
    const emptyEl = document.getElementById("historyEmpty");

    if (!listEl) return; // не на странице истории

    const STATUS_LABELS = {
        paid: "Оплачен",
        pending: "Ожидает",
        failed: "Не оплачен",
        expired: "Истёк",
    };

    function formatAmount(amount, currency) {
        const n = Number(amount);
        const formatted = n.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return `${formatted} ${currency === "RUB" ? "₽" : currency}`;
    }

    function formatDate(iso) {
        return new Date(iso).toLocaleString("ru-RU", {
            day: "numeric", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit",
        });
    }

    function renderRow(p) {
        const row = document.createElement("div");
        row.className = "history-row";
        const dateStr = formatDate(p.paid_at || p.created_at);
        const receiptLink =
            p.status === "paid"
                ? `<a class="history-receipt-link" href="/billing/success/?invoice=${p.id}">Открыть</a>`
                : "—";
        row.innerHTML = `
            <div>${dateStr}</div>
            <div>${p.package_title || "—"} · ${p.generations_granted} ген.</div>
            <div class="amount">${formatAmount(p.amount, p.currency)}</div>
            <div><span class="history-status ${p.status}">${STATUS_LABELS[p.status] || p.status}</span></div>
            <div>${receiptLink}</div>
        `;
        listEl.appendChild(row);
    }

    async function loadPayments() {
        try {
            const resp = await window.PhotoStudioAuth.authFetch(`${API_BASE}/payments/`);
            if (resp.status === 401) {
                window.location.href = "/login/?next=/billing/history/";
                return;
            }
            if (!resp.ok) throw new Error("bad response");
            const data = await resp.json();
            const payments = Array.isArray(data) ? data : data.results || [];

            if (!payments.length) {
                emptyEl.style.display = "block";
                return;
            }
            payments.forEach(renderRow);
        } catch (e) {
            emptyEl.textContent = "Не удалось загрузить историю платежей. Обновите страницу.";
            emptyEl.style.display = "block";
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        const loggedIn = window.PhotoStudioAuth && window.PhotoStudioAuth.isLoggedIn();
        if (!loggedIn) {
            window.location.href = "/login/?next=/billing/history/";
            return;
        }
        loadPayments();
    });
})();
