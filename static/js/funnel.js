/**
 * Этапы пути на /workstation → POST /api/funnel/ (apps/photos/views.FunnelEventView).
 * Нужны, чтобы видеть, на каком шаге уходят люди между «загрузил фото» и
 * «получил превью» — сервер сам видит только отправку заказа.
 * session_id живёт в localStorage и связывает этапы одного браузера, в том
 * числе до входа в аккаунт. keepalive — событие доходит, даже если человек
 * в этот момент уходит со страницы. Ошибки отправки молча игнорируются.
 */
(() => {
    const KEY = "sfj_funnel_session";
    let sessionId = "";
    try {
        sessionId = localStorage.getItem(KEY) || "";
        if (!sessionId) {
            sessionId = (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
            localStorage.setItem(KEY, sessionId);
        }
    } catch (e) {
        sessionId = "nostorage-" + Math.random().toString(36).slice(2);
    }

    function track(stage, meta, orderId) {
        try {
            // authFetch, а не fetch: с просроченным access-токеном (живёт 60 мин)
            // сервер отвечает 401 даже на открытый эндпоинт — authFetch обновит
            // токен, а если не выйдет, повторит запрос анонимно
            const send = window.PhotoStudioAuth ? window.PhotoStudioAuth.authFetch : fetch;
            send("/api/funnel/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                keepalive: true,
                body: JSON.stringify({ stage, session_id: sessionId, meta: meta || {}, order_id: orderId || undefined }),
            }).catch(() => {});
        } catch (e) { /* аналитика не должна ломать страницу */ }
    }

    window.SFJFunnel = { track, sessionId };
})();
