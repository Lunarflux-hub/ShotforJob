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

    window.SFJUnlock = { unlock, balanceText, startDownload };
})();
