/* رایان — ورود و ثبت‌نام */
(function () {
  "use strict";
  const { $, request, toast } = window.RAYAN;
  const isSignup = document.body.dataset.mode === "signup" || location.pathname.startsWith("/signup");

  const title = $("#auth-title");
  const sub = $("#auth-sub");
  const form = $("#auth-form");
  const nameField = $("#name-field");
  const submit = $("#auth-submit");
  const label = $("#submit-label");
  const errorEl = $("#auth-error");

  const identifierLabel = $("#identifier-label");
  const identifierHint = $("#identifier-hint");
  const identifierInput = $("#email");


  // ------------------------------------------------ نمایش نشان پس از ثبت‌نام
  function playWelcomeReel(next) {
    const reel = $("#welcome-reel");
    const skip = $("#welcome-skip");
    const close = $("#welcome-close");
    const full = $("#welcome-full");
    const progress = $("#welcome-progress");
    const hooks = [...document.querySelectorAll(".reel-hook")];
    if (!reel || !isSignup) {
      location.replace(next);
      return;
    }
    // ثانیه؛ همان ریتمی که نشان و کره حرکت می‌کنند (قابل تنظیم برای آزمون)
    const TOTAL = Number(window.RAYAN_REEL_MS || 8200) / 1000;
    let done = false;
    let started = 0;
    let raf = 0;
    const go = () => {
      if (done) return;
      done = true;
      cancelAnimationFrame(raf);
      try { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); } catch { /* نادیده */ }
      location.replace(next);
    };

    reel.hidden = false;
    document.body.classList.add("reel-open");
    reel.classList.add("is-playing");
    started = performance.now();
    const tick = () => {
      const t = (performance.now() - started) / 1000;
      if (progress) progress.style.width = `${Math.min(100, (t / TOTAL) * 100).toFixed(1)}%`;
      hooks.forEach((hook) => {
        const at = Number(hook.dataset.at || 0);
        hook.classList.toggle("is-on", t >= at && t < at + 2.6);
      });
      if (t >= TOTAL) { go(); return; }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    if (skip) {
      skip.setAttribute("href", next);
      skip.addEventListener("click", (event) => { event.preventDefault(); go(); });
    }
    close?.addEventListener("click", go);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") go();
    }, { once: true });

    if (full) {
      full.addEventListener("click", async () => {
        try {
          if (document.fullscreenElement) await document.exitFullscreen();
          else await (reel.requestFullscreen?.({ navigationUI: "hide" }) || reel.webkitRequestFullscreen?.());
        } catch { /* نادیده */ }
      });
      document.addEventListener("fullscreenchange", () => {
        full.setAttribute("aria-pressed", document.fullscreenElement ? "true" : "false");
        full.textContent = document.fullscreenElement ? "خروج از تمام‌صفحه" : "تمام‌صفحه";
      });
    }
    setTimeout(() => skip?.focus({ preventScroll: true }), 120);
  }

  const params = new URLSearchParams(location.search);
  const notice = $("\#auth-notice");
  const presetEmail = (params.get("email") || "").trim();

  if (isSignup) {
    document.title = "ساخت حساب · رایان";
    title.textContent = "ساخت حساب رایگان";
    sub.textContent = "یک حساب بساز تا گفتگوهایت بمانند و سهمیهٔ بیشتری بگیری.";
    nameField.hidden = false;
    label.textContent = "ساخت حساب";
    $("#password").autocomplete = "new-password";
    $("#switch-text").textContent = "حساب داری؟";
    $("#switch-link").textContent = "ورود";
    $("#switch-link").href = "/login";
    if (identifierLabel) identifierLabel.textContent = "ایمیل";
    if (identifierInput) {
      identifierInput.type = "email";
      identifierInput.autocomplete = "email";
    }
    if (identifierHint) identifierHint.textContent = "این ایمیل برای ورود و بازیابی حسابت استفاده می‌شود.";
    if (presetEmail && identifierInput) {
      identifierInput.value = presetEmail;
      if (notice) {
        notice.hidden = false;
        notice.textContent = "با این ایمیل هنوز حسابی ساخته نشده بود؛ همین‌جا در چند ثانیه بسازش.";
      }
      setTimeout(() => $("\#password")?.focus({ preventScroll: true }), 80);
    }
  } else if (identifierInput) {
    identifierInput.type = "text";
    identifierInput.autocomplete = "username";
  }

  $("#pw-toggle").addEventListener("click", () => {
    const input = $("#password");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    $("#pw-toggle").setAttribute("aria-label", show ? "پنهان‌کردن رمز" : "نمایش رمز");
  });

  function fail(message) {
    errorEl.textContent = message;
    errorEl.style.color = "var(--rose)";
  }

  // «من ربات نیستم» — اثبات‌کار محلی، بدون سرویس بیرونی
  const staticMode = !!(window.RAYAN.config && (window.RAYAN.config.static || window.RAYAN.config.offline));
  const humanBox = $("#human-slot");
  const humanWidget = humanBox && !staticMode && window.RAYAN && window.RAYAN.human
    ? window.RAYAN.human.mount(humanBox, { onState: (st) => { if (st.ready) errorEl.textContent = ""; } })
    : null;
  if (staticMode && humanBox) humanBox.hidden = true;

  async function checkExisting() {
    try {
      const me = await request("/api/auth/me");
      if (me.user) {
        location.replace("/chat");
      }
    } catch { /* آفلاین */ }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.textContent = "";
    const identifier = $("#email").value.trim();
    const password = $("#password").value;
    const name = $("#name").value.trim();
    const isEmail = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(identifier);

    if (isSignup && !isEmail) {
      fail("برای ساخت حساب یک ایمیل معتبر وارد کن.");
      return;
    }
    if (!identifier) {
      fail("ایمیل یا نام کاربری را وارد کن.");
      return;
    }
    if (!isSignup && identifier.includes("@") && !isEmail) {
      fail("ایمیل واردشده معتبر نیست.");
      return;
    }
    if (isSignup && password.length < 8) {
      fail("رمز عبور باید حداقل ۸ نویسه باشد.");
      return;
    }
    if (!password) {
      fail("رمز عبور را وارد کن.");
      return;
    }

    const proof = humanWidget ? humanWidget.value : null;
    if (!proof) {
      fail("برای ادامه، کادر «من ربات نیستم» را تأیید کن.");
      if (humanWidget) humanBox.scrollIntoView({ block: "center", behavior: "smooth" });
      return;
    }

    submit.disabled = true;
    const original = label.textContent;
    label.textContent = "لطفاً صبر کن…";
    try {
      const path = isSignup ? "/api/auth/register" : "/api/auth/login";
      const body = isSignup
        ? { name, email: identifier, password, captcha: proof }
        : { identifier, password, captcha: proof };
      const data = await request(path, { method: "POST", body });
      toast(isSignup ? "حسابت ساخته شد. خوش آمدی!" : `خوش برگشتی ${data.user.name || ""}!`, "ok");
      const next = new URLSearchParams(location.search).get("next");
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : null;
      if (data.admin) {
        toast("دسترسی مدیریت فعال شد.", "ok");
        setTimeout(() => location.replace(safeNext || "/admin"), 420);
        return;
      }
      if (isSignup && !safeNext) {
        setTimeout(() => playWelcomeReel("/chat"), 320);
        return;
      }
      setTimeout(() => location.replace(safeNext || "/chat"), 420);
    } catch (err) {
      const detail = err && err.data && err.data.detail;
      if (!isSignup && detail && typeof detail === "object" && detail.code === "account_not_found") {
        // حساب ساخته نشده است؛ مستقیم به پنل ثبت‌نام می‌رویم و ایمیل را از پیش پر می‌کنیم.
        const target = new URLSearchParams({ email: detail.email || identifier, from: "login" });
        const next = params.get("next");
        if (next && next.startsWith("/") && !next.startsWith("//")) target.set("next", next);
        location.replace(`/signup?${target.toString()}`);
        return;
      }
      fail(err.message);
      submit.disabled = false;
      label.textContent = original;
      // اثبات مصرف‌شده است؛ برای تلاش بعدی چالش تازه لازم است
      if (humanWidget) humanWidget.reset();
    }
  });

  if (staticMode) {
    if (notice) {
      notice.hidden = false;
      notice.textContent = "این نسخهٔ نمایشی روی GitHub Pages است؛ ورود و ساخت حساب فقط روی سرور فعال است.";
    }
    submit.disabled = true;
    label.textContent = "نسخهٔ نمایشی";
    $("#password").disabled = true;
    identifierInput.disabled = true;
  }

  checkExisting();
})();
