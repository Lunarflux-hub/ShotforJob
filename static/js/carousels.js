(() => {
    const API = "/api/carousels";
    const POLL_INTERVAL_MS = 3000;
    const $ = (id) => document.getElementById(id);

    const els = {
        loading: $("crLoading"), noAccess: $("crNoAccess"), app: $("crApp"),
        form: $("crForm"), topic: $("crTopic"), count: $("crCount"), handle: $("crHandle"),
        submit: $("crSubmit"), formError: $("crFormError"),
        result: $("crResult"), resultTitle: $("crResultTitle"),
        progress: $("crProgress"), progressText: $("crProgressText"), resultError: $("crResultError"),
        done: $("crDone"), slides: $("crSlides"), download: $("crDownload"),
        caption: $("crCaption"), copyCaption: $("crCopyCaption"),
        editSlides: $("crEditSlides"), editTheme: $("crEditTheme"), editHandle: $("crEditHandle"),
        rerender: $("crRerender"),
        historyCard: $("crHistoryCard"), history: $("crHistory"),
    };

    let current = null;
    let pollTimer = null;

    const authFetch = (url, options) =>
        (window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch)(url, options);

    function show(el, visible) { el.classList.toggle("d-none", !visible); }

    function showError(el, message) {
        el.textContent = message;
        show(el, !!message);
    }

    async function readError(resp, fallback) {
        try {
            const data = await resp.json();
            if (data.detail) return data.detail;
            const first = Object.values(data)[0];
            if (Array.isArray(first) && first.length) return String(first[0]);
        } catch (e) { /* не JSON */ }
        return fallback;
    }

    function formatDate(iso) {
        return new Date(iso).toLocaleString("ru-RU", {
            day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
        });
    }

    // ---------- Текущая карусель ----------
    function renderEditor(carousel) {
        els.editSlides.innerHTML = "";
        carousel.slides.forEach((slide, i) => {
            const box = document.createElement("div");
            box.className = "cr-edit-slide";

            const label = document.createElement("span");
            label.className = "cr-label";
            label.textContent = i === 0 ? "Слайд 1 · обложка" : `Слайд ${i + 1}`;

            const title = document.createElement("input");
            title.className = "cr-input";
            title.maxLength = 200;
            title.value = slide.title;
            title.dataset.field = "title";
            title.setAttribute("aria-label", `Заголовок слайда ${i + 1}`);

            const body = document.createElement("textarea");
            body.className = "cr-textarea";
            body.maxLength = 1000;
            body.value = slide.body;
            body.dataset.field = "body";
            body.setAttribute("aria-label", `Текст слайда ${i + 1}`);

            box.append(label, title, body);
            els.editSlides.appendChild(box);
        });
        els.editTheme.value = carousel.theme;
        els.editHandle.value = carousel.handle || "";
        els.caption.value = carousel.caption || "";
    }

    function renderCarousel(carousel) {
        current = carousel;
        show(els.result, true);
        els.resultTitle.textContent = carousel.topic;

        const busy = carousel.status === "pending" || carousel.status === "processing";
        show(els.progress, busy);
        els.rerender.disabled = busy;
        showError(els.resultError, carousel.status === "failed" ? (carousel.error_message || "Не удалось создать карусель") : "");

        if (carousel.status === "done") {
            els.slides.innerHTML = "";
            carousel.images.forEach((url, i) => {
                const img = document.createElement("img");
                img.src = url;
                img.alt = `Слайд ${i + 1}`;
                img.loading = "lazy";
                els.slides.appendChild(img);
            });
            renderEditor(carousel);
            show(els.done, true);
        } else if (!busy || !carousel.slides.length) {
            show(els.done, false);
        }
    }

    function stopPolling() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = null;
    }

    function startPolling(id) {
        stopPolling();
        pollTimer = setInterval(async () => {
            try {
                const resp = await authFetch(`${API}/${id}/`);
                if (!resp.ok) return; // единичный сбой — пробуем на следующем тике
                const carousel = await resp.json();
                renderCarousel(carousel);
                if (carousel.status === "done" || carousel.status === "failed") {
                    stopPolling();
                    els.submit.disabled = false;
                    loadHistory();
                }
            } catch (e) { /* сеть моргнула — следующий тик */ }
        }, POLL_INTERVAL_MS);
    }

    async function openCarousel(id) {
        const resp = await authFetch(`${API}/${id}/`);
        if (!resp.ok) return;
        const carousel = await resp.json();
        renderCarousel(carousel);
        els.result.scrollIntoView({ behavior: "smooth", block: "start" });
        if (carousel.status === "pending" || carousel.status === "processing") startPolling(id);
    }

    // ---------- Создание ----------
    els.form.addEventListener("submit", async (e) => {
        e.preventDefault();
        showError(els.formError, "");
        const topic = els.topic.value.trim();
        if (topic.length < 5) {
            showError(els.formError, "Опишите тему хотя бы парой слов");
            return;
        }

        els.submit.disabled = true;
        try {
            const resp = await authFetch(`${API}/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    topic,
                    slides_count: Number(els.count.value),
                    theme: els.form.querySelector("input[name=crTheme]:checked").value,
                    handle: els.handle.value.trim(),
                }),
            });
            if (!resp.ok) throw new Error(await readError(resp, "Не удалось создать карусель"));
            const carousel = await resp.json();
            show(els.done, false);
            els.progressText.textContent = "Пишем тексты и рисуем слайды… обычно до минуты";
            renderCarousel(carousel);
            els.result.scrollIntoView({ behavior: "smooth", block: "start" });
            startPolling(carousel.id);
        } catch (err) {
            showError(els.formError, err.message);
            els.submit.disabled = false;
        }
    });

    // ---------- Правки и пересборка ----------
    els.rerender.addEventListener("click", async () => {
        if (!current) return;
        const slides = [...els.editSlides.querySelectorAll(".cr-edit-slide")].map((box) => ({
            title: box.querySelector("[data-field=title]").value,
            body: box.querySelector("[data-field=body]").value,
        }));

        els.rerender.disabled = true;
        showError(els.resultError, "");
        try {
            const resp = await authFetch(`${API}/${current.id}/rerender/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slides,
                    theme: els.editTheme.value,
                    handle: els.editHandle.value.trim(),
                    caption: els.caption.value,
                }),
            });
            if (!resp.ok) throw new Error(await readError(resp, "Не удалось пересобрать слайды"));
            els.progressText.textContent = "Перерисовываем слайды…";
            renderCarousel(await resp.json());
            startPolling(current.id);
        } catch (err) {
            showError(els.resultError, err.message);
            els.rerender.disabled = false;
        }
    });

    // ---------- Скачивание и подпись ----------
    els.download.addEventListener("click", async () => {
        if (!current) return;
        els.download.disabled = true;
        try {
            // Скачиваем через fetch, а не ссылкой: API требует JWT в заголовке
            const resp = await authFetch(`${API}/${current.id}/download/`);
            if (!resp.ok) throw new Error("Не удалось скачать архив");
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `carousel-${current.id.slice(0, 8)}.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (err) {
            showError(els.resultError, err.message);
        } finally {
            els.download.disabled = false;
        }
    });

    els.copyCaption.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(els.caption.value);
            els.copyCaption.textContent = "Скопировано ✓";
        } catch (e) {
            els.caption.select();
            els.copyCaption.textContent = "Выделено — нажмите Ctrl+C";
        }
        setTimeout(() => { els.copyCaption.textContent = "Скопировать подпись"; }, 2000);
    });

    // ---------- История ----------
    const STATUS_LABELS = { pending: "в очереди", processing: "генерируется", done: "готово", failed: "ошибка" };

    async function loadHistory() {
        try {
            const resp = await authFetch(`${API}/`);
            if (!resp.ok) return;
            const items = await resp.json();
            els.history.innerHTML = "";
            items.forEach((c) => {
                const li = document.createElement("li");
                const btn = document.createElement("button");
                btn.type = "button";
                const topic = document.createElement("span");
                topic.className = "cr-history-topic";
                topic.textContent = c.topic;
                const meta = document.createElement("span");
                meta.className = "cr-history-meta";
                meta.textContent = `${c.slides_count} сл. · ${STATUS_LABELS[c.status] || c.status} · ${formatDate(c.created_at)}`;
                btn.append(topic, meta);
                btn.addEventListener("click", () => openCarousel(c.id));
                li.appendChild(btn);
                els.history.appendChild(li);
            });
            show(els.historyCard, items.length > 0);
        } catch (e) { /* история не критична */ }
    }

    // ---------- Старт ----------
    async function init() {
        if (!window.PhotoStudioAuth || !window.PhotoStudioAuth.isLoggedIn()) {
            window.location.href = "/login/?next=" + encodeURIComponent("/carousels/");
            return;
        }
        try {
            const resp = await authFetch(`${API}/access/`);
            const data = resp.ok ? await resp.json() : { enabled: false };
            show(els.loading, false);
            if (!data.enabled) {
                show(els.noAccess, true);
                return;
            }
            document.title = "Карусели для Instagram — ShotForJob";
            show(els.app, true);
            loadHistory();
        } catch (e) {
            show(els.loading, false);
            show(els.noAccess, true);
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})();
