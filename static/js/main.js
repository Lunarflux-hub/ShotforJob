(() => {
    const API_BASE = "/api";
    const POLL_INTERVAL_MS = 3000;

    const styleSelect = document.getElementById("styleSelect");
    const photoInput = document.getElementById("photoInput");
    const orderForm = document.getElementById("orderForm");
    const submitBtn = document.getElementById("submitBtn");
    const formError = document.getElementById("formError");

    const resultCard = document.getElementById("resultCard");
    const statusText = document.getElementById("statusText");
    const statusBadge = document.getElementById("statusBadge");
    const spinnerBlock = document.getElementById("spinnerBlock");
    const imageBlock = document.getElementById("imageBlock");
    const generatedImage = document.getElementById("generatedImage");
    const downloadBtn = document.getElementById("downloadBtn");
    const errorBlock = document.getElementById("errorBlock");
    const errorText = document.getElementById("errorText");
    const retryBtn = document.getElementById("retryBtn");
    const retryFromResultBtn = document.getElementById("retryFromResultBtn");
    const fbCount = document.getElementById("fbCount");
    const formBalanceRow = document.getElementById("formBalanceRow");

    let currentOrderId = null;
    let pollTimer = null;
    let currentBalance = null;

    async function loadBalance(attempt = 1) {
        if (!fbCount) return;
        const doFetch = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
        try {
            const resp = await doFetch(`${API_BASE}/billing/balance/`);
            // 429/5xx — это временная ошибка сервера/лимита, а не «баланс пропал»:
            // не рисуем «—», а тихо повторяем через паузу (до 3 попыток).
            if ((resp.status === 429 || resp.status >= 500) && attempt < 3) {
                setTimeout(() => loadBalance(attempt + 1), 1500 * attempt);
                return;
            }
            if (!resp.ok) throw new Error("bad response");
            const data = await resp.json();
            currentBalance = data.balance;
            fbCount.textContent = currentBalance;
            formBalanceRow.classList.toggle("fb-low", currentBalance <= 0);
        } catch (e) {
            fbCount.textContent = "—";
        }
    }

    const STATUS_LABELS = {
        pending: "в очереди",
        processing: "генерируется",
        done: "готово",
        failed: "ошибка",
    };

    const STATUS_BADGE_CLASSES = {
        pending: "bg-secondary",
        processing: "bg-info text-dark",
        done: "bg-success",
        failed: "bg-danger",
    };

    function showFormError(message) {
        formError.textContent = message;
        formError.classList.remove("d-none");
    }

    function hideFormError() {
        formError.classList.add("d-none");
    }

    function resetResultBlocks() {
        spinnerBlock.classList.add("d-none");
        imageBlock.classList.add("d-none");
        errorBlock.classList.add("d-none");
    }

    function setStatus(status) {
        statusText.textContent = STATUS_LABELS[status] || status;
        statusBadge.className = "badge mb-3 " + (STATUS_BADGE_CLASSES[status] || "bg-secondary");
    }

    async function loadStyles() {
        styleSelect.innerHTML = '<option value="" selected disabled>Загрузка стилей…</option>';
        try {
            const resp = await fetch(`${API_BASE}/styles/`);
            if (!resp.ok) throw new Error("Не удалось загрузить список стилей");
            const styles = await resp.json();

            if (!styles.length) {
                styleSelect.innerHTML = '<option value="" selected disabled>Нет доступных стилей</option>';
                return;
            }

            styleSelect.innerHTML = '<option value="" selected disabled>Выберите стиль…</option>';
            styles.forEach((style) => {
                const opt = document.createElement("option");
                opt.value = style.id;
                opt.textContent = style.name;
                styleSelect.appendChild(opt);
            });
        } catch (e) {
            styleSelect.innerHTML = '<option value="" selected disabled>Ошибка загрузки стилей</option>';
            showFormError(e.message);
        }
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    const MAX_POLL_ERRORS_IN_A_ROW = 5; // ~5 неудачных тиков подряд (15с при интервале 3с)
    let pollErrorStreak = 0;

    function startPolling(orderId) {
        stopPolling();
        pollErrorStreak = 0;
        pollTimer = setInterval(() => fetchOrderStatus(orderId), POLL_INTERVAL_MS);
    }

    async function fetchOrderStatus(orderId) {
        try {
            const doFetch = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
            const resp = await doFetch(`${API_BASE}/orders/${orderId}/`);
            if (!resp.ok) throw new Error("Не удалось получить статус заказа");
            const order = await resp.json();
            pollErrorStreak = 0; // успешный ответ — сбрасываем счётчик ошибок
            renderOrder(order);

            if (order.status === "done" || order.status === "failed") {
                stopPolling();
                submitBtn.disabled = false;
            }
        } catch (e) {
            // Единичная ошибка (например, 429 от общего лимита или сетевой сбой)
            // не означает, что генерация упала — она продолжается на сервере.
            // Прекращаем поллинг и показываем "ошибка" только после нескольких
            // неудач подряд, а не после самой первой.
            pollErrorStreak += 1;
            if (pollErrorStreak < MAX_POLL_ERRORS_IN_A_ROW) return;

            stopPolling();
            submitBtn.disabled = false;
            setStatus("failed");
            resetResultBlocks();
            errorText.textContent = e.message;
            errorBlock.classList.remove("d-none");
        }
    }

    function renderOrder(order) {
        resultCard.classList.remove("d-none");
        setStatus(order.status);
        resetResultBlocks();

        if (order.status === "pending" || order.status === "processing") {
            spinnerBlock.classList.remove("d-none");
            return;
        }

        if (order.status === "done") {
            const lastResult = order.results && order.results[0];
            if (lastResult) {
                generatedImage.src = lastResult.file_url;
                downloadBtn.href = lastResult.file_url;
                imageBlock.classList.remove("d-none");
            } else {
                setStatus("failed");
                errorText.textContent = "Результат не найден в ответе сервера";
                errorBlock.classList.remove("d-none");
            }
            return;
        }

        if (order.status === "failed") {
            errorText.textContent = order.error_message || "Не удалось сгенерировать фото";
            errorBlock.classList.remove("d-none");
        }
    }

    async function createOrder() {
        hideFormError();

        const styleId = styleSelect.value;
        const files = photoInput.files;

        if (!styleId) {
            showFormError("Выберите стиль");
            return;
        }
        if (files.length < 1 || files.length > 3) {
            showFormError("Загрузите от 1 до 3 фото");
            return;
        }

        const formData = new FormData();
        formData.append("style_id", styleId);
        for (const file of files) {
            formData.append("photos", file);
        }

        // ---- Одежда: обычный набор (кэжуал/деловой/спортивный) или
        // документный (пиджак/рубашка) — активен только один из блоков ----
        const clothingEl = document.querySelector(".clothing-option.selected")
            || document.querySelector(".doc-clothing-option.selected");
        if (clothingEl) {
            formData.append("clothing", clothingEl.dataset.value);
        }

        // ---- Фон: локация (офис/природа/сплошной цвет/своё изображение) ----
        const locationEl = document.querySelector(".location-option.selected");
        const docSelectedColor = document.getElementById("docSelectedColor");
        const isDocStyle = document.getElementById("docOptions")
            && document.getElementById("docOptions").classList.contains("doc-visible");

        if (locationEl) {
            const backgroundType = locationEl.dataset.value;
            formData.append("background_type", backgroundType);

            if (backgroundType === "solid") {
                const colorInput = document.getElementById("selectedColor");
                if (colorInput && colorInput.value) {
                    formData.append("background_color", colorInput.value);
                }
            } else if (backgroundType === "upload") {
                const bgFile = document.getElementById("bgImageInput").files[0];
                if (bgFile) {
                    formData.append("background_image", bgFile);
                }
            }
        } else if (isDocStyle && docSelectedColor && docSelectedColor.value) {
            // Документные стили: отдельного выбора локации нет, только цвет фона.
            formData.append("background_color", docSelectedColor.value);
        }

        submitBtn.disabled = true;
        submitBtn.textContent = "Отправка…";

        try {
            const doFetch = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
            const resp = await doFetch(`${API_BASE}/orders/`, {
                method: "POST",
                body: formData,
            });

            if (!resp.ok) {
                if (resp.status === 402) {
                    const err = await resp.json().catch(() => ({}));
                    showFormError(
                        `Недостаточно генераций на балансе (осталось ${err.balance ?? 0}). ` +
                        `Пополните баланс, чтобы продолжить.`
                    );
                    if (typeof err.balance === "number") {
                        currentBalance = err.balance;
                        if (fbCount) {
                            fbCount.textContent = currentBalance;
                            formBalanceRow.classList.add("fb-low");
                        }
                    }
                    submitBtn.disabled = false;
                    return;
                }
                const err = await resp.json().catch(() => ({}));
                const message = err.detail || Object.values(err)[0] || "Не удалось создать заказ";
                throw new Error(Array.isArray(message) ? message[0] : message);
            }

            const order = await resp.json();
            currentOrderId = order.id;
            renderOrder(order);
            startPolling(order.id);
            loadBalance();
        } catch (e) {
            showFormError(e.message);
            submitBtn.disabled = false;
        } finally {
            submitBtn.textContent = "Сгенерировать";
        }
    }

    async function retryOrder() {
        if (!currentOrderId) return;

        submitBtn.disabled = true;
        resetResultBlocks();
        setStatus("pending");
        spinnerBlock.classList.remove("d-none");

        try {
            const doFetch = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
            const resp = await doFetch(`${API_BASE}/orders/${currentOrderId}/retry/`, {
                method: "POST",
            });
            if (!resp.ok) throw new Error("Не удалось перезапустить генерацию");

            const order = await resp.json();
            renderOrder(order);
            startPolling(order.id);
        } catch (e) {
            submitBtn.disabled = false;
            setStatus("failed");
            resetResultBlocks();
            errorText.textContent = e.message;
            errorBlock.classList.remove("d-none");
        }
    }

    orderForm.addEventListener("submit", (e) => {
        e.preventDefault();
        createOrder();
    });

    retryBtn.addEventListener("click", retryOrder);
    retryFromResultBtn.addEventListener("click", retryOrder);

    loadStyles();
    loadBalance();
})();