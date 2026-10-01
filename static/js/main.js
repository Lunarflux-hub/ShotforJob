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
    const fbCount = document.getElementById("fbCount");
    const formBalanceRow = document.getElementById("formBalanceRow");
    const submitBtnText = document.getElementById("submitBtnText");
    const freePreviewHint = document.getElementById("freePreviewHint");
    const previewNote = document.getElementById("previewNote");
    const unlockMessage = document.getElementById("unlockMessage");
    const t = (ru, en) => (window.SFJ_t ? window.SFJ_t(ru, en) : ru);
    let freePreviewEligible = false;

    // Текст кнопки меняем во внутреннем span — textContent всей кнопки
    // стирал бы её анимацию (частицы/искры)
    function setSubmitText(text) {
        if (submitBtnText) submitBtnText.textContent = text;
        else submitBtn.textContent = text;
    }

    function idleSubmitText() {
        return freePreviewEligible
            ? t("Сгенерировать бесплатно", "Generate for free")
            : t("Сгенерировать", "Generate");
    }

    // Бесплатное превью (apps/photos/services/free_preview.py): новому
    // аккаунту первая генерация без списания, результат — со знаком
    async function loadFreePreviewStatus() {
        if (!window.PhotoStudioAuth || !window.PhotoStudioAuth.isLoggedIn()) return;
        try {
            const resp = await window.PhotoStudioAuth.authFetch(`${API_BASE}/orders/free-preview/`);
            if (!resp.ok) return;
            freePreviewEligible = !!(await resp.json()).eligible;
        } catch (e) {
            freePreviewEligible = false;
        }
        if (freePreviewHint) freePreviewHint.classList.toggle("d-none", !freePreviewEligible);
        if (!submitBtn.disabled) setSubmitText(idleSubmitText());
    }

    const reviewBlock = document.getElementById("reviewBlock");
    const reviewForm = document.getElementById("reviewForm");
    const reviewStars = document.querySelectorAll("#reviewStars .review-star");
    const reviewDetails = document.getElementById("reviewDetails");
    const reviewComment = document.getElementById("reviewComment");
    const reviewSubmit = document.getElementById("reviewSubmit");
    const reviewError = document.getElementById("reviewError");
    const reviewThanks = document.getElementById("reviewThanks");

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
                showResult(order, lastResult);
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

    // ---------- Результат: обычный или бесплатное превью ----------
    let currentOrder = null;

    const reportedPreviews = new Set();

    function showResult(order, result) {
        currentOrder = order;
        // Цель Метрики: готово бесплатное превью (один раз на заказ за визит страницы)
        if (order.is_free_preview && !reportedPreviews.has(order.id)) {
            reportedPreviews.add(order.id);
            window.ymReach && window.ymReach("preview_generated");
        }
        generatedImage.src = result.file_url;
        imageBlock.classList.remove("d-none");
        unlockMessage.classList.add("d-none");
        reviewBlock && reviewBlock.classList.add("d-none");  // новый результат — оценку спросим после скачивания
        applyResultState(result);
    }

    function applyResultState(result) {
        downloadBtn.dataset.resultId = result.id;
        const offers = document.getElementById("previewOffers");
        if (result.is_locked) {
            // Оригинал ещё не оплачен: вместо «Скачать» — оплата этого фото в один шаг
            downloadBtn.dataset.locked = "1";
            downloadBtn.classList.add("d-none");
            previewNote.classList.remove("d-none");
            reviewBlock && reviewBlock.classList.add("d-none");
            offers.classList.remove("d-none");
            window.SFJUnlock.renderLockedActions(offers, result.id, { onUnlocked: handleUnlocked });
        } else {
            offers.classList.add("d-none");
            downloadBtn.classList.remove("d-none");
            downloadBtn.dataset.locked = "";
            downloadBtn.setAttribute("download", "");
            downloadBtn.href = result.download_url || result.file_url;
            downloadBtn.textContent = t("Скачать", "Download");
            previewNote.classList.add("d-none");
            // Оценку просим после скачивания HD, а не сразу (см. askReviewAfterDownload)
            // «Ещё 5 вариантов в другом стиле» — только уже платившим (upsell.js)
            window.SFJUpsell && window.SFJUpsell.show(document.getElementById("upsellCard"));
        }
    }

    // Просим оценку после того, как человек скачал фото в HD (обычное или
    // разблокированное превью). Уже открытую форму повторно не сбрасываем.
    function askReviewAfterDownload() {
        if (currentOrder && reviewBlock && reviewBlock.classList.contains("d-none")) {
            setupReview(currentOrder);
        }
    }

    // Превью открылось с баланса (кнопка «Скачать в HD · 1 генерация» в unlock.js)
    function handleUnlocked(data) {
        generatedImage.src = data.result.file_url;
        applyResultState(data.result);
        if (data.charged) {
            unlockMessage.textContent = window.SFJUnlock.balanceText(data.balance);
            unlockMessage.classList.remove("d-none");
            loadBalance();
        }
        window.SFJUnlock.startDownload(data.result.download_url);
        askReviewAfterDownload();
    }

    downloadBtn.addEventListener("click", () => {
        askReviewAfterDownload();  // обычное скачивание идёт своим ходом по ссылке
    });

    // ---------- Отзыв о генерации ----------
    let reviewOrderId = null;
    let reviewRating = 0;

    function paintStars(value) {
        reviewStars.forEach((star) => {
            const on = Number(star.dataset.value) <= value;
            star.classList.toggle("active", on);
            star.setAttribute("aria-checked", String(Number(star.dataset.value) === value));
        });
    }

    function setupReview(order) {
        if (!reviewBlock) return;
        reviewOrderId = order.id;
        reviewRating = 0;
        reviewComment.value = "";
        reviewError.classList.add("d-none");
        reviewDetails.classList.add("d-none");
        paintStars(0);

        const alreadyReviewed = !!order.review;
        reviewForm.classList.toggle("d-none", alreadyReviewed);
        reviewThanks.classList.toggle("d-none", !alreadyReviewed);
        reviewBlock.classList.remove("d-none");
    }

    reviewStars.forEach((star) => {
        star.addEventListener("mouseenter", () => paintStars(Number(star.dataset.value)));
        star.addEventListener("mouseleave", () => paintStars(reviewRating));
        star.addEventListener("click", () => {
            reviewRating = Number(star.dataset.value);
            paintStars(reviewRating);
            reviewComment.placeholder = reviewRating <= 3
                ? "Что нам стоит улучшить? (необязательно)"
                : "Пара слов о результате (необязательно)";
            reviewDetails.classList.remove("d-none");
        });
    });

    if (reviewSubmit) {
        reviewSubmit.addEventListener("click", async () => {
            if (!reviewOrderId || !reviewRating) return;
            reviewSubmit.disabled = true;
            reviewError.classList.add("d-none");
            try {
                const doFetch = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
                const resp = await doFetch(`${API_BASE}/orders/${reviewOrderId}/review/`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ rating: reviewRating, comment: reviewComment.value.trim() }),
                });
                if (!resp.ok) throw new Error("Не удалось отправить отзыв, попробуйте ещё раз");
                reviewForm.classList.add("d-none");
                reviewThanks.classList.remove("d-none");
            } catch (e) {
                reviewError.textContent = e.message;
                reviewError.classList.remove("d-none");
            } finally {
                reviewSubmit.disabled = false;
            }
        });
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
        setSubmitText(t("Отправка…", "Sending…"));

        try {
            const doFetch = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
            const resp = await doFetch(`${API_BASE}/orders/`, {
                method: "POST",
                body: formData,
            });

            if (!resp.ok) {
                if (resp.status === 402) {
                    const err = await resp.json().catch(() => ({}));
                    showFormError(t(
                        `Недостаточно генераций на балансе (осталось ${err.balance ?? 0}). ` +
                        `Пополните баланс, чтобы продолжить.`,
                        `Not enough generations on your balance (${err.balance ?? 0} left). Top up to continue.`
                    ));
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
            renderOrder(order);
            startPolling(order.id);
            loadBalance();
            if (order.is_free_preview) {
                freePreviewEligible = false;
                freePreviewHint && freePreviewHint.classList.add("d-none");
            }
        } catch (e) {
            showFormError(e.message);
            submitBtn.disabled = false;
        } finally {
            setSubmitText(idleSubmitText());
        }
    }

    orderForm.addEventListener("submit", (e) => {
        e.preventDefault();
        createOrder();
    });

    loadStyles();
    loadBalance();
    loadFreePreviewStatus();

    document.addEventListener("sfj:lang", () => {
        if (!submitBtn.disabled) setSubmitText(idleSubmitText());
        if (downloadBtn.dataset.resultId) {
            downloadBtn.textContent = t("Скачать", "Download");
        }
    });
})();