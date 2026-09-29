/**
 * Допродажа «Ещё 5 вариантов в другом стиле — 149 ₽» после результата
 * (/workstation, /results). Пакет с visibility=paid_only API отдаёт только
 * тем, кто уже платил (apps/billing/catalog.can_buy) — если его нет в ответе,
 * блок просто не показывается. Цена и количество — из БД.
 * Зависит от window.PhotoStudioAuth (auth.js).
 */
(() => {
    const t = (ru, en) => (window.SFJ_t ? window.SFJ_t(ru, en) : ru);
    let cached = null;

    async function findUpsell() {
        if (cached !== null) return cached;
        cached = undefined;
        if (!window.PhotoStudioAuth || !window.PhotoStudioAuth.isLoggedIn()) return cached;
        try {
            const resp = await window.PhotoStudioAuth.authFetch("/api/billing/config/");
            if (resp.ok) {
                const data = await resp.json();
                cached = data.packages.find((p) => p.visibility === "paid_only");
            }
        } catch (e) { /* без допродажи — не критично */ }
        return cached;
    }

    function fill(container, pkg) {
        const price = Number(pkg.price) % 1 === 0 ? Number(pkg.price).toFixed(0) : pkg.price;
        container.querySelector(".upsell-title").textContent = t(
            `Ещё ${pkg.generations} вариантов в другом стиле — ${price} ₽`,
            `${pkg.generations} more variations in another style — ${price} ₽`
        );
        container.querySelector(".upsell-sub").textContent = t(
            `~${pkg.per_photo} ₽ за фото — для тех, кто уже с нами`,
            `~${pkg.per_photo} ₽ per photo — for existing customers`
        );
        const link = container.querySelector(".upsell-btn");
        link.href = `/payment/?package=${encodeURIComponent(pkg.slug)}`;
        link.textContent = t("Оплатить", "Pay");
    }

    /** Показывает блок в container (разметка — .upsell-title/.upsell-sub/.upsell-btn), если допродажа доступна. */
    async function show(container) {
        if (!container) return;
        const pkg = await findUpsell();
        if (!pkg) return;
        fill(container, pkg);
        container.classList.remove("d-none");
        document.addEventListener("sfj:lang", () => fill(container, pkg));
    }

    window.SFJUpsell = { show };
})();
