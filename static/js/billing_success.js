/**
 * Логика страницы /billing/success/ — псевдо-чек после оплаты через PayAnyWay.
 * Реальный фискальный чек присылает сама Moneta.ru на почту — здесь только
 * дизайн подтверждения. Зависит от window.PhotoStudioAuth (auth.js).
 */
(() => {
    const API_BASE = "/api/billing";
    const POLL_INTERVAL_MS = 2000;
    const POLL_TIMEOUT_MS = 30000;

    const loadingEl = document.getElementById("receiptLoading");
    const errorEl = document.getElementById("receiptError");
    const errorTextEl = document.getElementById("receiptErrorText");
    const ticketEl = document.getElementById("receiptTicket");
    const actionsEl = document.getElementById("receiptActions");
    const confettiEl = document.getElementById("receiptConfetti");

    if (!loadingEl) return; // не на странице чека

    const CONFETTI_COLORS = ["#ef4444", "#3b82f6", "#22c55e", "#eab308", "#8b5cf6", "#f97316"];

    function launchConfetti() {
        const count = 90;
        for (let i = 0; i < count; i++) {
            const el = document.createElement("i");
            el.style.left = Math.random() * 100 + "%";
            el.style.background = CONFETTI_COLORS[i % CONFETTI_COLORS.length];
            const duration = 2.5 + Math.random() * 2.5;
            const delay = Math.random() * 1.5;
            el.style.animationDuration = duration + "s";
            el.style.animationDelay = delay + "s";
            confettiEl.appendChild(el);
        }
        setTimeout(() => { confettiEl.innerHTML = ""; }, 7000);
    }

    // Детерминированный псевдо-штрихкод — только оформление, без реального
    // фискального смысла (настоящий чек шлёт Moneta.ru на почту).
    function drawBarcode(svg, value) {
        let hash = 0;
        for (let i = 0; i < value.length; i++) {
            hash = (hash << 5) - hash + value.charCodeAt(i);
            hash |= 0;
        }
        const seededRandom = (seed) => {
            const x = Math.sin(seed) * 10000;
            return x - Math.floor(x);
        };

        const barCount = 60;
        const spacing = 1.5;
        const bars = [];
        for (let i = 0; i < barCount; i++) {
            const r = seededRandom(hash + i);
            bars.push(r > 0.7 ? 2.5 : 1.5);
        }
        const totalWidth = bars.reduce((acc, w) => acc + w + spacing, 0) - spacing;
        const svgWidth = 250;
        let x = (svgWidth - totalWidth) / 2;

        svg.innerHTML = "";
        bars.forEach((w) => {
            const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            rect.setAttribute("x", x);
            rect.setAttribute("y", "10");
            rect.setAttribute("width", w);
            rect.setAttribute("height", "50");
            rect.setAttribute("fill", "#000");
            svg.appendChild(rect);
            x += w + spacing;
        });
    }

    function formatAmount(amount, currency) {
        const n = Number(amount);
        const formatted = n.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return `${formatted} ${currency === "RUB" ? "₽" : currency}`;
    }

    function formatDate(iso) {
        const d = new Date(iso);
        return d.toLocaleString("ru-RU", {
            day: "numeric", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit",
        });
    }

    function showTicket(payment) {
        loadingEl.style.display = "none";
        errorEl.style.display = "none";
        ticketEl.style.display = "block";
        actionsEl.style.display = "flex";

        const ticketId = String(payment.id).padStart(10, "0");
        document.getElementById("rTicketId").textContent = "#" + ticketId;
        document.getElementById("rAmount").textContent = formatAmount(payment.amount, payment.currency);
        document.getElementById("rDate").textContent = formatDate(payment.paid_at || payment.created_at);
        document.getElementById("rGenerations").textContent =
            (payment.package_title ? payment.package_title + " · " : "") + `${payment.generations_granted} ген.`;

        const barcodeValue = ticketId;
        document.getElementById("rBarcodeValue").textContent = barcodeValue;
        drawBarcode(document.getElementById("rBarcode"), barcodeValue);

        launchConfetti();
    }

    function showError(text) {
        loadingEl.style.display = "none";
        ticketEl.style.display = "none";
        actionsEl.style.display = "none";
        errorEl.style.display = "block";
        if (text) errorTextEl.textContent = text;
    }

    async function fetchPayment(id) {
        const resp = await window.PhotoStudioAuth.authFetch(`${API_BASE}/payments/${id}/`);
        if (resp.status === 401) throw new Error("auth");
        if (!resp.ok) return null;
        return resp.json();
    }

    // Оплата из «Скачать в HD»: вебхук уже списал 1 генерацию и открыл фото
    async function showUnlockedPhoto(payment) {
        if (!payment.unlock_result_id || !payment.unlock_done || !window.SFJUnlock) return;
        const box = document.getElementById("receiptUnlock");
        const text = document.getElementById("receiptUnlockText");
        const btn = document.getElementById("receiptUnlockBtn");
        try {
            const resp = await window.PhotoStudioAuth.authFetch(`${API_BASE}/balance/`);
            const balance = resp.ok ? (await resp.json()).balance : null;
            text.textContent = balance === null
                ? (window.SFJ_t ? window.SFJ_t("Фото разблокировано", "Photo unlocked") : "Фото разблокировано")
                : window.SFJUnlock.balanceText(balance);
        } catch (e) { /* без баланса — просто кнопка */ }
        box.style.display = "block";
        btn.addEventListener("click", async () => {
            btn.disabled = true;
            try {
                // Фото уже открыто — повторный вызов ничего не списывает, только отдаёт ссылку
                const data = await window.SFJUnlock.unlock(payment.unlock_result_id);
                if (data) window.SFJUnlock.startDownload(data.result.download_url);
            } finally {
                btn.disabled = false;
            }
        });
    }

    // Цель purchase — только после оплаты, подтверждённой вебхуком (сюда
    // попадаем при status=paid), с суммой. Сервер разрешает отправку ровно
    // один раз на платёж и не для тестовых — перезагрузка не задублирует.
    async function reportPurchase(paymentId) {
        try {
            const resp = await window.PhotoStudioAuth.authFetch(`${API_BASE}/payments/${paymentId}/purchase-goal/`, { method: "POST" });
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.report && window.ymReach) {
                window.ymReach("purchase", {
                    order_price: Number(data.order_price),
                    currency: data.currency || "RUB",
                    package: data.package,
                });
            }
        } catch (e) { /* аналитика не должна ломать чек */ }
    }

    async function pollPayment(id) {
        const startedAt = Date.now();

        while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
            let payment;
            try {
                payment = await fetchPayment(id);
            } catch (e) {
                showError("Сессия истекла — войдите заново, чтобы увидеть чек.");
                return;
            }

            if (!payment) {
                showError("Платёж не найден.");
                return;
            }

            if (payment.status === "paid") {
                showTicket(payment);
                showUnlockedPhoto(payment);
                reportPurchase(payment.id);
                if (window.PhotoStudioAuth) window.PhotoStudioAuth.refreshBalance();
                return;
            }

            if (payment.status === "failed" || payment.status === "expired") {
                showError("Платёж не прошёл. Попробуйте оплатить ещё раз.");
                return;
            }

            await new Promise((res) => setTimeout(res, POLL_INTERVAL_MS));
        }

        showError("Оплата ещё обрабатывается. Проверьте статус в истории платежей чуть позже.");
    }

    document.addEventListener("DOMContentLoaded", () => {
        const loggedIn = window.PhotoStudioAuth && window.PhotoStudioAuth.isLoggedIn();
        if (!loggedIn) {
            // Оплата из письма-напоминания часто идёт без входа на сайт: после
            // входа возвращаем на этот же чек (фото в HD уже ушло на почту)
            window.location.href = "/login/?next=" + encodeURIComponent(location.pathname + location.search);
            return;
        }

        const params = new URLSearchParams(window.location.search);
        // Основной путь — редирект через наш сервер (/api/billing/payanyway/success/),
        // который кладёт чистый ?invoice=. Но если в ЛК Moneta.ru Success URL
        // настроен прямо на эту страницу, придут её сырые параметры — поддерживаем и это.
        const invoice = params.get("invoice") || params.get("MNT_TRANSACTION_ID");
        if (!invoice) {
            showError("Не передан номер платежа.");
            return;
        }

        pollPayment(invoice);
    });
})();
