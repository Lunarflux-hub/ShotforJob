/**
 * Общий модуль авторизации PhotoStudio (ShotForJob).
 * Подключается на ЛЮБОЙ странице (лендинг, /login/, /workstation/).
 * Все обработчики ищут элементы по id и просто ничего не делают, если их
 * нет на текущей странице — поэтому один файл безопасно грузить везде.
 *
 * Использование в других скриптах (например main.js):
 *   window.PhotoStudioAuth.getAccessToken()
 *   window.PhotoStudioAuth.isLoggedIn()
 *   window.PhotoStudioAuth.getProfile()  -> {name, email, picture} | null
 *
 * Ожидаемая разметка в шапке (необязательна — если элементов нет, просто
 * ничего не произойдёт):
 *   <a id="authHeaderBtn" href="/login/">
 *     <img id="authAvatarImg" src=".../user-icon.png">
 *   </a>
 *   <span id="authUserName"></span>
 */
(() => {
    const API_BASE = "/api";
    const ACCESS_TOKEN_KEY = "photostudio_access_token";
    const REFRESH_TOKEN_KEY = "photostudio_refresh_token";
    const PROFILE_KEY = "photostudio_user_profile"; // JSON: {name, email, picture}

    let defaultAvatarSrc = null; // запоминаем иконку по умолчанию при первой отрисовке

    function getProfile() {
        try {
            return JSON.parse(localStorage.getItem(PROFILE_KEY) || "null");
        } catch {
            return null;
        }
    }

    function saveSession(access, refresh, profile) {
        localStorage.setItem(ACCESS_TOKEN_KEY, access);
        localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
        localStorage.setItem(PROFILE_KEY, JSON.stringify(profile || {}));
        updateHeaderWidget();
        updateBalanceWidget();
    }

    function clearSession() {
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
        localStorage.removeItem(PROFILE_KEY);
        updateHeaderWidget();
        updateBalanceWidget();
    }

    async function refreshAccessToken() {
        const refresh = localStorage.getItem(REFRESH_TOKEN_KEY);
        if (!refresh) return null;

        try {
            const resp = await fetch(`${API_BASE}/auth/refresh/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh }),
            });
            if (!resp.ok) return null;
            const data = await resp.json();
            localStorage.setItem(ACCESS_TOKEN_KEY, data.access);
            return data.access;
        } catch {
            return null;
        }
    }

    /**
     * Обёртка над fetch(), которая сама прикрепляет Authorization и лечит
     * просроченный/невалидный access-токен:
     * 1) получили 401 -> пробуем обновить токен через refresh
     * 2) refresh тоже не сработал (просрочен/невалиден) -> разлогиниваем и
     *    повторяем запрос уже БЕЗ токена (большинство эндпоинтов поддерживают
     *    анонимный доступ, так что действие всё равно выполнится).
     */
    async function authFetch(url, options = {}) {
        options.headers = { ...(options.headers || {}) };

        let token = localStorage.getItem(ACCESS_TOKEN_KEY);
        console.debug("[authFetch]", url, "token найден:", !!token, token ? token.slice(0, 20) + "…" : null);
        if (token) options.headers["Authorization"] = `Bearer ${token}`;

        let resp = await fetch(url, options);
        console.debug("[authFetch] ответ:", resp.status, "для", url);
        if (resp.status !== 401 || !token) return resp;

        console.debug("[authFetch] получили 401, пробуем refresh…");
        const newToken = await refreshAccessToken();
        if (newToken) {
            console.debug("[authFetch] refresh успешен, повторяем запрос");
            options.headers["Authorization"] = `Bearer ${newToken}`;
            return fetch(url, options);
        }

        console.debug("[authFetch] refresh не удался, разлогиниваем и пробуем анонимно");
        clearSession();
        delete options.headers["Authorization"];
        return fetch(url, options);
    }

    window.PhotoStudioAuth = {
        getAccessToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),
        getProfile,
        isLoggedIn: () => !!localStorage.getItem(ACCESS_TOKEN_KEY),
        logout: clearSession,
        authFetch,
        refreshBalance: updateBalanceWidget,
    };

    // ---------- Шапка: бейдж баланса генераций ----------
    async function updateBalanceWidget(attempt = 1) {
        const badge = document.getElementById("balanceBadge");
        const countEl = document.getElementById("balanceBadgeCount");
        if (!badge) return; // на этой странице нет шапки с бейджем

        if (!window.PhotoStudioAuth.isLoggedIn()) {
            badge.style.display = "none";
            return;
        }

        badge.style.display = "flex";
        try {
            const resp = await authFetch(`${API_BASE}/billing/balance/`);
            // 429/5xx — временный сбой, а не «баланс обнулился»: молча повторяем
            if ((resp.status === 429 || resp.status >= 500) && attempt < 3) {
                setTimeout(() => updateBalanceWidget(attempt + 1), 1500 * attempt);
                return;
            }
            if (!resp.ok) throw new Error("bad response");
            const data = await resp.json();
            countEl.textContent = data.balance;
        } catch (e) {
            countEl.textContent = "—";
        }
    }

    // ---------- Шапка: аватар + имя + состояние кнопки ----------
    function updateHeaderWidget() {
        const btn = document.getElementById("authHeaderBtn");
        const avatarImg = document.getElementById("authAvatarImg");
        const nameEl = document.getElementById("authUserName");
        if (!btn) return; // на этой странице нет шапки с авторизацией

        if (avatarImg && defaultAvatarSrc === null) {
            defaultAvatarSrc = avatarImg.getAttribute("src");
            // Если картинка аватара не загрузится (CORS/referrer/битая ссылка у
            // провайдера), браузер молча покажет alt-текст вместо неё — поэтому
            // держим alt нейтральным и откатываемся на дефолтную иконку по ошибке.
            avatarImg.addEventListener("error", () => {
                if (avatarImg.src !== defaultAvatarSrc) {
                    avatarImg.src = defaultAvatarSrc;
                    avatarImg.alt = "Аватар";
                }
            });
        }

        if (window.PhotoStudioAuth.isLoggedIn()) {
            const profile = getProfile() || {};
            const displayName = profile.name || profile.email || "Пользователь";

            btn.href = "#";
            btn.dataset.authState = "in";
            btn.setAttribute("aria-label", "Выйти из аккаунта");
            btn.title = `Вы вошли как ${displayName}. Нажмите, чтобы выйти`;

            if (avatarImg) {
                avatarImg.src = profile.picture || defaultAvatarSrc;
                avatarImg.alt = "Аватар";
            }
            if (nameEl) {
                nameEl.textContent = displayName;
                nameEl.style.display = "";
            }
        } else {
            btn.href = "/login/";
            btn.dataset.authState = "out";
            btn.removeAttribute("title");
            btn.setAttribute("aria-label", "Войти");

            if (avatarImg) {
                avatarImg.src = defaultAvatarSrc;
                avatarImg.alt = "Войти";
            }
            if (nameEl) {
                nameEl.textContent = "";
                nameEl.style.display = "none";
            }
        }
    }

    document.addEventListener("click", (e) => {
        const btn = e.target.closest("#authHeaderBtn");
        if (!btn || btn.dataset.authState !== "in") return;
        e.preventDefault();
        if (confirm("Выйти из аккаунта?")) window.PhotoStudioAuth.logout();
    });

    // ---------- Email/пароль: логин и регистрация (страница /login/) ----------
    // ТЕСТОВЫЙ вход по email/паролю (email == логин), для интеграции с
    // платёжкой. При откате — просто вернуть старый вариант этого блока.
    async function loginWithPassword(email, password) {
        const resp = await fetch(`${API_BASE}/auth/login/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            const firstError = Object.values(err)[0];
            throw new Error(
                err.detail ||
                    (Array.isArray(firstError) ? firstError[0] : null) ||
                    "Неверный email или пароль"
            );
        }
        const tokens = await resp.json();
        // Обычный логин по паролю не отдаёт аватар — используем email
        saveSession(tokens.access, tokens.refresh, { name: email, email });
    }

    async function registerAndLogin(email, password) {
        const resp = await fetch(`${API_BASE}/auth/register/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            const firstError = Object.values(err)[0];
            throw new Error(
                (Array.isArray(firstError) ? firstError[0] : null) ||
                    err.detail ||
                    "Не удалось зарегистрироваться"
            );
        }
        // /api/auth/register/ не возвращает JWT — логинимся сразу теми же данными
        await loginWithPassword(email, password);
    }

    function bindLoginForm() {
        const form = document.getElementById("loginForm");
        if (!form) return;
        const errorBox = document.getElementById("loginError");

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            errorBox.style.display = "none";
            try {
                await loginWithPassword(
                    form.querySelector("[name=email]").value.trim(),
                    form.querySelector("[name=password]").value
                );
                window.location.href = "/";
            } catch (err) {
                errorBox.textContent = err.message;
                errorBox.style.display = "block";
            }
        });
    }

    function bindRegisterForm() {
        const form = document.getElementById("registerForm");
        if (!form) return;
        const errorBox = document.getElementById("registerError");

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            errorBox.style.display = "none";
            try {
                await registerAndLogin(
                    form.querySelector("[name=email]").value.trim(),
                    form.querySelector("[name=password]").value
                );
                window.location.href = "/";
            } catch (err) {
                errorBox.textContent = err.message;
                errorBox.style.display = "block";
            }
        });
    }

    function bindAuthToggle() {
        const toggleBtn = document.getElementById("authToggleModeBtn");
        const loginForm = document.getElementById("loginForm");
        const registerForm = document.getElementById("registerForm");
        if (!toggleBtn || !loginForm || !registerForm) return;

        toggleBtn.addEventListener("click", () => {
            const showingLogin = loginForm.style.display !== "none";
            loginForm.style.display = showingLogin ? "none" : "flex";
            registerForm.style.display = showingLogin ? "flex" : "none";
            toggleBtn.textContent = showingLogin
                ? "Уже есть аккаунт? Войти"
                : "Нет аккаунта? Зарегистрироваться";
        });
    }

    // ---------- Google Identity Services (вызывается их скриптом напрямую) ----------
    window.handleGoogleLogin = async function (response) {
        try {
            const resp = await fetch(`${API_BASE}/auth/google/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ id_token: response.credential }),
            });
            if (!resp.ok) throw new Error("Не удалось войти через Google");
            const data = await resp.json();
            saveSession(data.access, data.refresh, data.profile);
            window.location.href = "/";
        } catch (e) {
            alert(e.message);
        }
    };

    // ---------- Yandex ID: implicit flow ----------
    function startYandexLogin() {
        const clientId = window.YANDEX_OAUTH_CLIENT_ID;
        if (!clientId) {
            alert("Yandex OAuth client_id не настроен (YANDEX_OAUTH_CLIENT_ID в .env)");
            return;
        }
        const redirectUri = window.location.origin + window.location.pathname;
        const authUrl =
            `https://oauth.yandex.ru/authorize?response_type=token` +
            `&client_id=${encodeURIComponent(clientId)}` +
            `&redirect_uri=${encodeURIComponent(redirectUri)}`;
        window.location.href = authUrl;
    }

    async function handleYandexRedirect() {
        if (!window.location.hash.includes("access_token")) return;

        const params = new URLSearchParams(window.location.hash.slice(1));
        const accessToken = params.get("access_token");
        if (!accessToken) return;

        window.history.replaceState(null, "", window.location.pathname);

        try {
            const resp = await fetch(`${API_BASE}/auth/yandex/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ access_token: accessToken }),
            });
            if (!resp.ok) throw new Error("Не удалось войти через Yandex ID");
            const data = await resp.json();
            saveSession(data.access, data.refresh, data.profile);
            window.location.href = "/";
        } catch (e) {
            alert(e.message);
        }
    }

    function initMobileMenu() {
        const toggle = document.getElementById("menuToggle");
        const menu = document.querySelector(".header .menu");
        if (!toggle || !menu) return;

        function closeMenu() {
            menu.classList.remove("open");
            toggle.classList.remove("open");
            toggle.setAttribute("aria-expanded", "false");
        }

        toggle.addEventListener("click", (e) => {
            e.stopPropagation();
            const isOpen = menu.classList.toggle("open");
            toggle.classList.toggle("open", isOpen);
            toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
        });

        document.addEventListener("click", (e) => {
            if (!menu.classList.contains("open")) return;
            if (!menu.contains(e.target) && e.target !== toggle && !toggle.contains(e.target)) {
                closeMenu();
            }
        });

        menu.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", closeMenu);
        });

        window.addEventListener("resize", () => {
            if (window.innerWidth > 768) closeMenu();
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        updateHeaderWidget();
        updateBalanceWidget();
        bindLoginForm();
        bindRegisterForm();
        bindAuthToggle();
        initMobileMenu();

        const yandexBtn = document.getElementById("yandexLoginBtn");
        if (yandexBtn) yandexBtn.addEventListener("click", startYandexLogin);

        handleYandexRedirect();
    });
})();