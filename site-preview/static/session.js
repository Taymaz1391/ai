/* رایان — نگه‌داریِ نشست مستقل از کوکی.
 *
 * برخی مرورگرها/پیش‌نمایش‌ها کوکیِ همان سایت را در iframe یا حالتِ بدونِ کوکیِ
 * سوم‌شخص ذخیره نمی‌کنند؛ نتیجه‌اش این می‌شود که کاربر وارد می‌شود اما سایت
 * هنوز او را «مهمان» می‌بیند. این فایل توکنِ نشست را در localStorage نگه
 * می‌دارد و روی همهٔ درخواست‌های /api می‌فرستد.
 */
(function () {
  "use strict";

  const SESSION_KEY = "rayan.session";
  const ADMIN_KEY = "rayan.admin";
  const CSRF_KEY = "rayan.csrf";

  function safeGet(key) {
    try { return window.localStorage.getItem(key) || ""; } catch { return ""; }
  }
  function safeSet(key, value) {
    try {
      if (value) window.localStorage.setItem(key, value);
      else window.localStorage.removeItem(key);
    } catch { /* حالتِ خصوصی: فقط کوکی می‌ماند */ }
  }

  const api = {
    token: () => safeGet(SESSION_KEY),
    admin: () => safeGet(ADMIN_KEY),
    csrf: () => safeGet(CSRF_KEY),
    save(data) {
      if (!data || typeof data !== "object") return;
      if (data.token) safeSet(SESSION_KEY, data.token);
      if (data.admin_token) safeSet(ADMIN_KEY, data.admin_token);
      if (data.csrf) safeSet(CSRF_KEY, data.csrf);
    },
    clear() {
      safeSet(SESSION_KEY, "");
      safeSet(ADMIN_KEY, "");
      safeSet(CSRF_KEY, "");
    },
  };
  window.RAYAN_SESSION = api;

  // هر درخواستِ هم‌دامنه به /api با توکنِ ذخیره‌شده می‌رود؛ کوکی همچنان کار می‌کند.
  const nativeFetch = window.fetch ? window.fetch.bind(window) : null;
  if (!nativeFetch) return;

  window.fetch = function (input, init) {
    try {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      const sameOrigin = !/^[a-z]+:\/\//i.test(url) || url.startsWith(window.location.origin);
      if (sameOrigin && url.indexOf("/api/") !== -1) {
        const options = Object.assign({}, init || {});
        const headers = new Headers(options.headers || (input && input.headers) || {});
        const token = api.token();
        const admin = api.admin();
        const csrf = api.csrf();
        if (token && !headers.has("Authorization")) headers.set("Authorization", "Bearer " + token);
        if (admin && !headers.has("X-Rayyan-Admin")) headers.set("X-Rayyan-Admin", admin);
        if (csrf && !headers.has("X-Rayyan-Csrf")) headers.set("X-Rayyan-Csrf", csrf);
        options.headers = headers;
        return nativeFetch(input, options);
      }
    } catch { /* در بدترین حالت، درخواستِ اصلی فرستاده می‌شود */ }
    return nativeFetch(input, init);
  };
})();
