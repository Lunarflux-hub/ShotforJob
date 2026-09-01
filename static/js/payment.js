/**
 * Логика страницы /payment/ — покупка пакетов генераций через PayAnyWay.
 * Свободная сумма не поддерживается — только готовые пакеты.
 * Зависит от window.PhotoStudioAuth (auth.js), должен подключаться после него.
 */
(() => {
    const API_BASE = "/api/billing";

    let config = null;
    let selectedPackageId = null;

    const packagesEl = document.getElementById("paymentPackages");
    const payBtn = document.getElementById("paymentPayBtn");
    const messageEl = document.getElementById("paymentMessage");
    const guestNoticeEl = document.getElementById("paymentGuestNotice");
    const payanywayForm = document.getElementById("paymentPayanywayForm");

    if (!packagesEl) return; // не на странице /payment/

    function showMessage(text, type) {
        messageEl.textContent = text;
        messageEl.className = "payment-message " + (type || "error");
    }

    function clearMessage() {
        messageEl.textContent = "";
        messageEl.className = "payment-message";
    }

    function renderPackages() {
        packagesEl.innerHTML = "";
        if (!config.packages.length) {
            packagesEl.innerHTML =
                '<div class="payment-empty-note">Пакеты пока не настроены. Загляните позже.</div>';
            return;
        }
        config.packages.forEach((pkg) => {
            const card = document.createElement("div");
            card.className = "payment-package";
            card.dataset.packageId = pkg.id;
            card.innerHTML = `
                <div class="pkg-title">${pkg.title}</div>
                <div class="pkg-generations">${pkg.generations} генераций</div>
                <div class="pkg-price">${pkg.price} ₽</div>
            `;
            card.addEventListener("click", () => selectPackage(pkg.id, card));
            packagesEl.appendChild(card);
        });
    }

    function selectPackage(id, cardEl) {
        selectedPackageId = id;
        document
            .querySelectorAll(".payment-package")
            .forEach((el) => el.classList.remove("selected"));
        cardEl.classList.add("selected");
        updatePayButton();
    }

    function updatePayButton() {
        const loggedIn = window.PhotoStudioAuth && window.PhotoStudioAuth.isLoggedIn();
        payBtn.disabled = !loggedIn || selectedPackageId === null;
        payBtn.textContent = selectedPackageId === null ? "Выберите пакет" : "Оплатить";
    }

    async function loadConfig() {
        try {
            const resp = await fetch(`${API_BASE}/config/`);
            if (!resp.ok) throw new Error("Не удалось загрузить пакеты");
            config = await resp.json();
        } catch (e) {
            showMessage("Не удалось загрузить пакеты. Обновите страницу.", "error");
            return;
        }

        renderPackages();
        updatePayButton();
    }

    async function submitPayment() {
        clearMessage();
        payBtn.disabled = true;
        payBtn.textContent = "Создаём платёж…";

        try {
            const resp = await window.PhotoStudioAuth.authFetch(`${API_BASE}/topup/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ package_id: selectedPackageId }),
            });

            if (resp.status === 401) {
                showMessage("Сессия истекла — войдите заново.", "error");
                return;
            }

            const data = await resp.json();
            if (!resp.ok) {
                const errors = {
                    package_id_required: "Выберите пакет.",
                    invalid_package: "Пакет не найден или отключён.",
                };
                showMessage(errors[data.error] || "Не удалось создать платёж.", "error");
                return;
            }

            // Собираем и отправляем форму на PayAnyWay
            payanywayForm.action = data.action_url;
            payanywayForm.method = data.method || "POST";
            payanywayForm.innerHTML = "";
            Object.entries(data.fields).forEach(([key, value]) => {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = key;
                input.value = value;
                payanywayForm.appendChild(input);
            });

            showMessage("Перенаправляем на страницу оплаты PayAnyWay…", "info");
            payanywayForm.submit();
        } catch (e) {
            showMessage("Ошибка сети. Попробуйте ещё раз.", "error");
        } finally {
            updatePayButton();
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        const loggedIn = window.PhotoStudioAuth && window.PhotoStudioAuth.isLoggedIn();
        if (!loggedIn) {
            guestNoticeEl.style.display = "block";
        }
        payBtn.addEventListener("click", submitPayment);
        loadConfig();
    });
})();
