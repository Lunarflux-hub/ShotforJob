/**
 * «Скачать в HD» для бесплатного превью — общий для /workstation и /results.
 * POST /api/results/<id>/unlock/: есть генерации — списывается 1 и приходит
 * ссылка на оригинал; нет — переходим на оплату «Оптимального» с этим фото
 * (после оплаты вебхук разблокирует его сам, см. apps/billing/views.py).
 * Зависит от window.PhotoStudioAuth (auth.js).
 */
(() => {
    const t = (ru, en) => (window.SFJ_t ? window.SFJ_t(ru, en) : ru);

    function balanceText(balance) {
        if (!balance) return t("Фото разблокировано — скачивание началось", "Photo unlocked — download started");
        return t(
            `Фото разблокировано, на балансе осталось ${balance} ${plural(balance, "генерация", "генерации", "генераций")}`,
            `Photo unlocked — ${balance} ${balance === 1 ? "generation" : "generations"} left on your balance`
        );
    }

    function plural(n, one, few, many) {
        const mod10 = n % 10, mod100 = n % 100;
        if (mod10 === 1 && mod100 !== 11) return one;
        if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
        return many;
    }

    function startDownload(url) {
        const a = document.createElement("a");
        a.href = url;
        a.rel = "noopener";
        document.body.appendChild(a);
        a.click();
        a.remove();
    }

    /**
     * Возвращает { result, balance, charged } после успешной разблокировки;
     * при нехватке генераций уводит на оплату и возвращает null.
     */
    async function unlock(resultId) {
        const resp = await window.PhotoStudioAuth.authFetch(`/api/results/${resultId}/unlock/`, { method: "POST" });
        if (resp.status === 402) {
            const data = await resp.json().catch(() => ({}));
            window.location.href = data.pay_url || `/payment/?package=optimal&unlock=${resultId}`;
            return null;
        }
        if (!resp.ok) throw new Error(t("Не удалось открыть фото. Попробуйте ещё раз.", "Couldn't unlock the photo. Please try again."));
        return resp.json();
    }

    // ---------- Оплата превью в один шаг ----------
    // Под превью: «Скачать это фото в HD — 49 ₽» и рядом «5 фото за 199 ₽».
    // Обе сразу создают платёж с разблокировкой этого фото и уходят на
    // PayAnyWay — без страницы тарифов. Пакеты и цены — из /api/billing/config/.
    let offersPromise = null;

    function loadOffers() {
        if (!offersPromise) {
            offersPromise = (async () => {
                const [configResp, balanceResp] = await Promise.all([
                    window.PhotoStudioAuth.authFetch("/api/billing/config/"),
                    window.PhotoStudioAuth.authFetch("/api/billing/balance/"),
                ]);
                const config = configResp.ok ? await configResp.json() : { packages: [] };
                const byId = (id) => config.packages.find((p) => p.id === id) || null;
                const offers = config.unlock_offers || {};
                return {
                    single: byId(offers.single),
                    bundle: byId(offers.bundle),
                    balance: balanceResp.ok ? (await balanceResp.json()).balance : 0,
                };
            })().catch(() => ({ single: null, bundle: null, balance: 0 }));
        }
        return offersPromise;
    }

    const priceText = (pkg) => {
        const n = Number(pkg.promo_price || pkg.price);
        return n % 1 === 0 ? n.toFixed(0) : n.toFixed(2);
    };

    async function payAndUnlock(resultId, pkg, btn) {
        btn.disabled = true;
        const price = Number(priceText(pkg));
        window.ymReach && window.ymReach("pay_click", { package: pkg.slug, price, unlock: true });
        try {
            const resp = await window.PhotoStudioAuth.authFetch("/api/billing/topup/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ package_id: pkg.id, unlock_result_id: resultId }),
            });
            if (!resp.ok) throw new Error();
            const data = await resp.json();
            const form = document.createElement("form");
            form.action = data.action_url;
            form.method = data.method || "POST";
            form.style.display = "none";
            Object.entries(data.fields).forEach(([key, value]) => {
                const input = document.createElement("input");
                input.type = "hidden";
                input.name = key;
                input.value = value;
                form.appendChild(input);
            });
            document.body.appendChild(form);
            const goal = { package_id: pkg.id, price };
            if (window.ymGoal) window.ymGoal("payment", goal, () => form.submit());
            else form.submit();
        } catch (e) {
            btn.disabled = false;
            // Запасной путь — страница тарифов с этим фото
            window.location.href = `/payment/?package=${encodeURIComponent(pkg.slug)}&unlock=${resultId}`;
        }
    }

    function button(cls, text, onClick) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = cls;
        b.textContent = text;
        b.addEventListener("click", () => onClick(b));
        return b;
    }

    /**
     * Рисует в container кнопки для неоплаченного превью.
     * opts.onUnlocked(data) — вызывается, если фото открылось с баланса.
     */
    async function renderLockedActions(container, resultId, opts = {}) {
        const { single, bundle, balance } = await loadOffers();

        const draw = () => {
            container.replaceChildren();
            container.classList.add("preview-offers");
            if (balance >= 1 || !single) {
                // Генерации уже есть (или цены не загрузились) — открываем с баланса
                container.appendChild(button("btn-pill primary", balance >= 1
                    ? t("Скачать в HD · 1 генерация", "Download in HD · 1 generation")
                    : t("Скачать в HD", "Download in HD"), async (b) => {
                    b.disabled = true;
                    try {
                        const data = await unlock(resultId);
                        if (data && opts.onUnlocked) opts.onUnlocked(data);
                    } catch (e) {
                        b.disabled = false;
                    }
                }));
                return;
            }
            container.appendChild(button("btn-pill primary offer-main",
                t(`Скачать это фото в HD — ${priceText(single)} ₽`, `Download this photo in HD — ${priceText(single)} ₽`),
                (b) => payAndUnlock(resultId, single, b)));
            if (bundle) {
                const extra = bundle.generations - 1;
                const alt = button("btn-pill secondary offer-alt",
                    t(`${bundle.generations} фото за ${priceText(bundle)} ₽`, `${bundle.generations} photos for ${priceText(bundle)} ₽`),
                    (b) => payAndUnlock(resultId, bundle, b));
                alt.title = t(`Это фото и ещё ${extra} в других стилях`, `This photo plus ${extra} more in other styles`);
                const hint = document.createElement("span");
                hint.className = "offer-hint";
                hint.textContent = t(`это фото + ещё ${extra}`, `this photo + ${extra} more`);
                const wrap = document.createElement("span");
                wrap.className = "offer-alt-wrap";
                wrap.append(alt, hint);
                container.appendChild(wrap);
            }
        };
        draw();
        if (!container.dataset.langBound) {
            container.dataset.langBound = "1";
            document.addEventListener("sfj:lang", () => container.isConnected && draw());
        }
    }

    window.SFJUnlock = { unlock, balanceText, startDownload, renderLockedActions };
})();
