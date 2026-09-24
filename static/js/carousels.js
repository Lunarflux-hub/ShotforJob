(() => {
    const API = "/api/carousels";
    const POLL_INTERVAL_MS = 3000;
    const PREVIEW_DEBOUNCE_MS = 350;
    const MAX_BLOCKS = 20;
    const DESIGN_STORAGE_KEY = "sfj_carousel_design";
    const $ = (id) => document.getElementById(id);

    const LAYOUTS = {
        cover: "Обложка",
        text: "Текст",
        list: "Список",
        stat: "Цифра",
        quote: "Цитата",
        cta: "Призыв",
    };
    // Какие поля показывать в блоке для каждого макета: [поле, подпись, тип]
    const FIELDS = {
        cover: [["emoji"], ["title", "Заголовок", "input"], ["body", "Подзаголовок", "textarea"]],
        text: [["emoji"], ["title", "Заголовок", "input"], ["body", "Текст", "textarea"]],
        list: [["emoji"], ["title", "Заголовок", "input"], ["items", "Пункты — по одному в строке, можно начинать с эмодзи", "textarea"]],
        stat: [["emoji"], ["value", "Цифра (например «7 сек», «80%»)", "input"], ["title", "Что она значит", "input"], ["body", "Пояснение", "textarea"]],
        quote: [["body", "Цитата", "textarea"], ["title", "Автор или источник", "input"]],
        cta: [["emoji"], ["title", "Заголовок", "input"], ["body", "Текст", "textarea"], ["value", "Текст кнопки", "input"]],
    };
    const QUICK_EMOJI = ["✨", "🔥", "💡", "✅", "📌", "🚀", "💼", "📸", "👀", "🎯", "⚡", "❤️"];

    const els = {
        loading: $("crLoading"), noAccess: $("crNoAccess"), app: $("crApp"),
        form: $("crForm"), topic: $("crTopic"), count: $("crCount"), handle: $("crHandle"),
        submit: $("crSubmit"), formError: $("crFormError"),
        themes: $("crThemes"), accent: $("crAccent"), accentReset: $("crAccentReset"), pattern: $("crPattern"),
        result: $("crResult"), resultTitle: $("crResultTitle"), dirty: $("crDirty"),
        save: $("crSave"), download: $("crDownload"),
        progress: $("crProgress"), progressText: $("crProgressText"), resultError: $("crResultError"),
        editor: $("crEditor"), blocks: $("crBlocks"), addBlock: $("crAddBlock"),
        caption: $("crCaption"), copyCaption: $("crCopyCaption"),
        historyCard: $("crHistoryCard"), history: $("crHistory"),
    };

    let options = { themes: [], design: {} };
    const state = { theme: "light", design: {} };
    let current = null;          // карусель с сервера
    let blocks = [];             // слайды в редакторе (объекты, которые правит пользователь)
    let dirty = false;
    let busy = false;
    let downloadAfterSave = false;
    let pollTimer = null;
    const previews = new Map();  // блок -> { img, timer, controller, url }

    const authFetch = (url, opts) =>
        (window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch)(url, opts);

    function show(el, visible) { el.classList.toggle("d-none", !visible); }
    function showError(el, message) { el.textContent = message; show(el, !!message); }

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
        return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
    }

    function blankSlide(layout) {
        return { layout, emoji: "", title: "", body: "", items: [], value: "" };
    }

    // ================= Оформление =================
    function saveDesignLocally() {
        try { localStorage.setItem(DESIGN_STORAGE_KEY, JSON.stringify({ theme: state.theme, design: state.design })); } catch (e) { /* приватный режим */ }
    }

    function loadDesignLocally() {
        try { return JSON.parse(localStorage.getItem(DESIGN_STORAGE_KEY) || "null"); } catch (e) { return null; }
    }

    function themeAccent() {
        const theme = options.themes.find((t) => t.key === state.theme);
        return theme ? theme.accent : "#0066FF";
    }

    function renderThemeButtons() {
        els.themes.innerHTML = "";
        options.themes.forEach((theme) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "cr-theme-btn";
            btn.dataset.theme = theme.key;
            const swatch = document.createElement("span");
            swatch.className = "cr-theme-swatch";
            swatch.style.background = theme.background.length > 1
                ? `linear-gradient(135deg, ${theme.background[0]}, ${theme.background[1]})`
                : theme.background[0];
            swatch.style.color = theme.text;
            swatch.textContent = "Аа";
            const dot = document.createElement("i");
            dot.style.background = theme.accent;
            swatch.appendChild(dot);
            const label = document.createElement("span");
            label.textContent = theme.label;
            btn.append(swatch, label);
            btn.addEventListener("click", () => {
                state.theme = theme.key;
                designChanged();
            });
            els.themes.appendChild(btn);
        });
    }

    function syncDesignControls() {
        els.themes.querySelectorAll(".cr-theme-btn").forEach((btn) =>
            btn.setAttribute("aria-pressed", String(btn.dataset.theme === state.theme)));
        els.accent.value = state.design.accent || themeAccent();
        els.accentReset.classList.toggle("d-none", !state.design.accent);
        els.pattern.value = state.design.pattern;
        document.querySelectorAll(".cr-seg[data-design]").forEach((seg) => {
            seg.querySelectorAll("button").forEach((b) =>
                b.setAttribute("aria-pressed", String(b.dataset.value === state.design[seg.dataset.design])));
        });
        document.querySelectorAll("input[type=checkbox][data-design]").forEach((box) => {
            box.checked = !!state.design[box.dataset.design];
        });
    }

    function designChanged() {
        syncDesignControls();
        saveDesignLocally();
        if (blocks.length) {
            markDirty();
            refreshAllPreviews();
        }
    }

    function bindDesignControls() {
        document.querySelectorAll(".cr-seg[data-design]").forEach((seg) => {
            seg.addEventListener("click", (e) => {
                const btn = e.target.closest("button");
                if (!btn) return;
                state.design[seg.dataset.design] = btn.dataset.value;
                designChanged();
            });
        });
        document.querySelectorAll("input[type=checkbox][data-design]").forEach((box) => {
            box.addEventListener("change", () => {
                state.design[box.dataset.design] = box.checked;
                designChanged();
            });
        });
        els.pattern.addEventListener("change", () => { state.design.pattern = els.pattern.value; designChanged(); });
        els.accent.addEventListener("input", () => { state.design.accent = els.accent.value.toUpperCase(); designChanged(); });
        els.accentReset.addEventListener("click", () => { state.design.accent = ""; designChanged(); });
        els.handle.addEventListener("input", () => {
            if (blocks.length) { markDirty(); refreshAllPreviews(); }
        });
    }

    // ================= Превью блоков =================
    function schedulePreview(block, delay = PREVIEW_DEBOUNCE_MS) {
        const entry = previews.get(block);
        if (!entry) return;
        clearTimeout(entry.timer);
        entry.img.classList.add("loading");
        entry.timer = setTimeout(() => loadPreview(block), delay);
    }

    function refreshAllPreviews() {
        blocks.forEach((block) => schedulePreview(block));
    }

    async function loadPreview(block) {
        const entry = previews.get(block);
        if (!entry) return;
        if (entry.controller) entry.controller.abort();
        entry.controller = new AbortController();
        try {
            const resp = await authFetch(`${API}/preview/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                signal: entry.controller.signal,
                body: JSON.stringify({
                    slide: block,
                    index: blocks.indexOf(block),
                    total: blocks.length,
                    theme: state.theme,
                    design: state.design,
                    handle: els.handle.value.trim(),
                }),
            });
            if (!resp.ok) return;
            const url = URL.createObjectURL(await resp.blob());
            if (entry.url) URL.revokeObjectURL(entry.url);
            entry.url = url;
            entry.img.src = url;
            entry.img.classList.remove("loading");
        } catch (e) { /* отменён более новым запросом или сеть моргнула */ }
    }

    // ================= Блоки =================
    function markDirty() {
        dirty = true;
        show(els.dirty, true);
        els.download.textContent = "Сохранить и скачать";
    }

    function markClean() {
        dirty = false;
        show(els.dirty, false);
        els.download.textContent = "Скачать ZIP";
    }

    function fieldInput(block, field, label, type) {
        const wrap = document.createElement("div");
        wrap.className = "cr-field";
        const lab = document.createElement("label");
        lab.className = "cr-label";
        lab.textContent = label;
        const input = document.createElement(type === "textarea" ? "textarea" : "input");
        input.className = type === "textarea" ? "cr-textarea" : "cr-input";
        input.value = field === "items" ? (block.items || []).join("\n") : (block[field] || "");
        input.maxLength = field === "items" ? 600 : field === "value" ? 60 : field === "title" ? 200 : 1000;
        const id = `crf-${Math.random().toString(36).slice(2, 9)}`;
        input.id = id;
        lab.htmlFor = id;
        input.addEventListener("input", () => {
            block[field] = field === "items" ? input.value.split("\n") : input.value;
            markDirty();
            schedulePreview(block);
        });
        wrap.append(lab, input);
        return wrap;
    }

    function emojiInput(block) {
        const wrap = document.createElement("div");
        wrap.className = "cr-field";
        const lab = document.createElement("span");
        lab.className = "cr-label";
        lab.textContent = "Эмодзи слайда";
        const row = document.createElement("div");
        row.className = "cr-emoji-row";
        const input = document.createElement("input");
        input.className = "cr-input";
        input.maxLength = 16;
        input.value = block.emoji || "";
        input.setAttribute("aria-label", "Эмодзи слайда");
        input.addEventListener("input", () => { block.emoji = input.value.trim(); markDirty(); schedulePreview(block); });
        row.appendChild(input);
        QUICK_EMOJI.forEach((emoji) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "cr-emoji-pick";
            btn.textContent = emoji;
            btn.setAttribute("aria-label", `Поставить ${emoji}`);
            btn.addEventListener("click", () => {
                block.emoji = emoji;
                input.value = emoji;
                markDirty();
                schedulePreview(block, 0);
            });
            row.appendChild(btn);
        });
        wrap.append(lab, row);
        return wrap;
    }

    function iconButton(symbol, label, handler, disabled) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cr-icon-btn";
        btn.textContent = symbol;
        btn.title = label;
        btn.setAttribute("aria-label", label);
        btn.disabled = !!disabled;
        btn.addEventListener("click", handler);
        return btn;
    }

    function structureChanged() {
        markDirty();
        renderBlocks();
        refreshAllPreviews();  // номера и счётчик «N/всего» зависят от позиции
    }

    function renderBlocks() {
        // Превью-картинки переиспользуем, чтобы при перестановке не мигали
        const old = new Map(previews);
        previews.clear();
        els.blocks.innerHTML = "";

        blocks.forEach((block, i) => {
            const box = document.createElement("div");
            box.className = "cr-block";

            const prevEntry = old.get(block);
            const img = prevEntry ? prevEntry.img : document.createElement("img");
            img.className = "cr-block-preview" + (prevEntry ? "" : " loading");
            img.alt = `Превью слайда ${i + 1}`;
            // auto — после загрузки берутся настоящие пропорции картинки, 4/5 или 1/1 — только до неё
            if (!prevEntry) img.style.aspectRatio = state.design.aspect === "square" ? "auto 1 / 1" : "auto 4 / 5";
            previews.set(block, prevEntry ? { ...prevEntry } : { img, timer: null, controller: null, url: null });
            old.delete(block);

            const fields = document.createElement("div");
            const head = document.createElement("div");
            head.className = "cr-block-head";
            const num = document.createElement("span");
            num.className = "cr-block-num";
            num.textContent = `Слайд ${i + 1}`;
            const layoutSelect = document.createElement("select");
            layoutSelect.className = "cr-select";
            layoutSelect.setAttribute("aria-label", `Макет слайда ${i + 1}`);
            Object.entries(LAYOUTS).forEach(([key, label]) => {
                const opt = document.createElement("option");
                opt.value = key;
                opt.textContent = label;
                layoutSelect.appendChild(opt);
            });
            layoutSelect.value = block.layout;
            layoutSelect.addEventListener("change", () => {
                block.layout = layoutSelect.value;
                markDirty();
                renderBlocks();
                schedulePreview(block, 0);
            });

            head.append(
                num,
                layoutSelect,
                iconButton("↑", "Переместить выше", () => { [blocks[i - 1], blocks[i]] = [blocks[i], blocks[i - 1]]; structureChanged(); }, i === 0),
                iconButton("↓", "Переместить ниже", () => { [blocks[i + 1], blocks[i]] = [blocks[i], blocks[i + 1]]; structureChanged(); }, i === blocks.length - 1),
                iconButton("⧉", "Дублировать", () => {
                    blocks.splice(i + 1, 0, JSON.parse(JSON.stringify(block)));
                    structureChanged();
                }, blocks.length >= MAX_BLOCKS),
                iconButton("✕", "Удалить слайд", () => { blocks.splice(i, 1); structureChanged(); }, blocks.length <= 1),
            );
            fields.appendChild(head);

            FIELDS[block.layout].forEach(([field, label, type]) => {
                fields.appendChild(field === "emoji" ? emojiInput(block) : fieldInput(block, field, label, type));
            });

            box.append(img, fields);
            els.blocks.appendChild(box);
        });

        // Удалённые блоки: отменяем их запросы и освобождаем картинки
        old.forEach((entry) => {
            clearTimeout(entry.timer);
            if (entry.controller) entry.controller.abort();
            if (entry.url) URL.revokeObjectURL(entry.url);
        });
        els.addBlock.disabled = blocks.length >= MAX_BLOCKS;
    }

    els.addBlock.addEventListener("click", () => {
        if (blocks.length >= MAX_BLOCKS) return;
        // Новый блок встаёт перед финальным призывом, если он есть
        const last = blocks[blocks.length - 1];
        const at = last && last.layout === "cta" ? blocks.length - 1 : blocks.length;
        blocks.splice(at, 0, blankSlide("text"));
        structureChanged();
    });

    // ================= Карусель =================
    function setBusy(isBusy, text) {
        busy = isBusy;
        show(els.progress, isBusy);
        if (text) els.progressText.textContent = text;
        els.save.disabled = isBusy;
        els.download.disabled = isBusy;
    }

    function loadIntoEditor(carousel) {
        current = carousel;
        blocks = (carousel.slides || []).map((s, i) => ({
            ...blankSlide(i === 0 ? "cover" : "text"),
            ...s,
            items: Array.isArray(s.items) ? [...s.items] : [],
        }));
        state.theme = carousel.theme;
        state.design = { ...options.design, ...(carousel.design || {}) };
        els.handle.value = carousel.handle || "";
        els.caption.value = carousel.caption || "";
        syncDesignControls();
        renderBlocks();
        refreshAllPreviews();
        markClean();
        show(els.editor, true);
    }

    function applyCarousel(carousel, { reloadEditor }) {
        show(els.result, true);
        els.resultTitle.textContent = carousel.topic;
        const inProgress = carousel.status === "pending" || carousel.status === "processing";
        setBusy(inProgress);
        showError(els.resultError, carousel.status === "failed" ? (carousel.error_message || "Не удалось создать карусель") : "");
        if (carousel.status === "done") {
            current = carousel;
            if (reloadEditor) loadIntoEditor(carousel);
        } else if (!inProgress && !blocks.length) {
            show(els.editor, false);
        }
    }

    function stopPolling() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = null;
    }

    function startPolling(id, { reloadEditor }) {
        stopPolling();
        pollTimer = setInterval(async () => {
            try {
                const resp = await authFetch(`${API}/${id}/`);
                if (!resp.ok) return;  // единичный сбой — пробуем на следующем тике
                const carousel = await resp.json();
                applyCarousel(carousel, { reloadEditor });
                if (carousel.status === "done" || carousel.status === "failed") {
                    stopPolling();
                    els.submit.disabled = false;
                    loadHistory();
                    if (carousel.status === "done" && downloadAfterSave) {
                        downloadAfterSave = false;
                        downloadZip();
                    }
                }
            } catch (e) { /* сеть моргнула — следующий тик */ }
        }, POLL_INTERVAL_MS);
    }

    async function openCarousel(id) {
        if (dirty && !window.confirm("Несохранённые изменения пропадут. Открыть другую карусель?")) return;
        const resp = await authFetch(`${API}/${id}/`);
        if (!resp.ok) return;
        const carousel = await resp.json();
        blocks = [];
        renderBlocks();
        show(els.editor, false);
        applyCarousel(carousel, { reloadEditor: true });
        els.result.scrollIntoView({ behavior: "smooth", block: "start" });
        if (busy) startPolling(id, { reloadEditor: true });
    }

    els.form.addEventListener("submit", async (e) => {
        e.preventDefault();
        showError(els.formError, "");
        const topic = els.topic.value.trim();
        if (topic.length < 5) {
            showError(els.formError, "Опишите тему хотя бы парой слов");
            return;
        }
        if (dirty && !window.confirm("Несохранённые изменения текущей карусели пропадут. Продолжить?")) return;

        els.submit.disabled = true;
        try {
            const resp = await authFetch(`${API}/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    topic,
                    slides_count: Number(els.count.value),
                    theme: state.theme,
                    design: state.design,
                    handle: els.handle.value.trim(),
                }),
            });
            if (!resp.ok) throw new Error(await readError(resp, "Не удалось создать карусель"));
            const carousel = await resp.json();
            blocks = [];
            renderBlocks();
            markClean();
            show(els.editor, false);
            applyCarousel(carousel, { reloadEditor: true });
            setBusy(true, "Пишем тексты и рисуем слайды… обычно до минуты");
            els.result.scrollIntoView({ behavior: "smooth", block: "start" });
            startPolling(carousel.id, { reloadEditor: true });
        } catch (err) {
            showError(els.formError, err.message);
            els.submit.disabled = false;
        }
    });

    async function saveCarousel() {
        if (!current || busy) return false;
        showError(els.resultError, "");
        const slides = blocks.map((b) => ({
            ...b,
            items: (b.items || []).map((s) => s.trim()).filter(Boolean),
        }));
        setBusy(true, "Сохраняем и перерисовываем слайды…");
        try {
            const resp = await authFetch(`${API}/${current.id}/rerender/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slides,
                    theme: state.theme,
                    design: state.design,
                    handle: els.handle.value.trim(),
                    caption: els.caption.value,
                }),
            });
            if (!resp.ok) throw new Error(await readError(resp, "Не удалось сохранить"));
            current = await resp.json();
            markClean();
            // Редактор не перезагружаем — пользователь может продолжать правки
            startPolling(current.id, { reloadEditor: false });
            return true;
        } catch (err) {
            setBusy(false);
            showError(els.resultError, err.message);
            return false;
        }
    }

    els.save.addEventListener("click", saveCarousel);
    els.caption.addEventListener("input", markDirty);

    async function downloadZip() {
        els.download.disabled = true;
        try {
            // Через fetch, а не ссылкой: API требует JWT в заголовке
            const resp = await authFetch(`${API}/${current.id}/download/`);
            if (!resp.ok) throw new Error("Не удалось скачать архив");
            const url = URL.createObjectURL(await resp.blob());
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
            els.download.disabled = busy;
        }
    }

    els.download.addEventListener("click", async () => {
        if (!current) return;
        if (dirty) {
            downloadAfterSave = await saveCarousel();
            return;
        }
        downloadZip();
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

    window.addEventListener("beforeunload", (e) => {
        if (dirty) { e.preventDefault(); e.returnValue = ""; }
    });

    // ================= История =================
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

    // ================= Старт =================
    async function init() {
        if (!window.PhotoStudioAuth || !window.PhotoStudioAuth.isLoggedIn()) {
            window.location.href = "/login/?next=" + encodeURIComponent("/carousels/");
            return;
        }
        try {
            const access = await authFetch(`${API}/access/`);
            const data = access.ok ? await access.json() : { enabled: false };
            if (!data.enabled) throw new Error("no access");
            const resp = await authFetch(`${API}/options/`);
            if (!resp.ok) throw new Error("no options");
            options = await resp.json();
        } catch (e) {
            show(els.loading, false);
            show(els.noAccess, true);
            return;
        }

        const saved = loadDesignLocally();
        state.theme = saved && options.themes.some((t) => t.key === saved.theme) ? saved.theme : "light";
        state.design = { ...options.design, ...((saved && saved.design) || {}) };

        document.title = "Карусели для Instagram — ShotForJob";
        renderThemeButtons();
        bindDesignControls();
        syncDesignControls();
        show(els.loading, false);
        show(els.app, true);
        loadHistory();
    }

    document.addEventListener("DOMContentLoaded", init);
})();
