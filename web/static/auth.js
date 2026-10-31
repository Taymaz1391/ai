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

  // -------------------------------------------------------- ورود با کلید API
  const keyToggle = $("#key-toggle");
  const keyForm = $("#key-form");
  const keyError = $("#key-error");
  if (keyToggle && keyForm) {
    keyToggle.addEventListener("click", () => {
      const open = keyForm.hidden;
      keyForm.hidden = !open;
      keyToggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) $("#api-key")?.focus({ preventScroll: true });
    });
    const submitKey = async () => {
      const raw = ($("#api-key").value || "").trim();
      keyError.textContent = "";
      if (!/^rk_[A-Za-z0-9_-]{16,}$/.test(raw)) {
        keyError.textContent = "کلید باید با rk_ شروع شود؛ کلید را کامل کپی کن.";
        return;
      }
      const submit = $("#key-submit");
      submit.disabled = true;
      submit.textContent = "بررسی…";
      try {
        const me = await request("/api/auth/me", { headers: { "x-api-key": raw } });
        if (!me || !me.user) throw new Error("این کلید به حسابی متصل نیست.");
        window.RAYAN.apiKey(raw);
        toast(`خوش آمدی ${me.user.name || ""}! دسترسی با کلید API فعال شد.`, "ok");
        const next = new URLSearchParams(location.search).get("next");
        const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/chat";
        setTimeout(() => location.replace(safeNext), 420);
      } catch (err) {
        keyError.textContent = err.message || "کلید معتبر نیست.";
        submit.disabled = false;
        submit.textContent = "ورود با کلید";
      }
    };
    $("#key-submit").addEventListener("click", submitKey);
    $("#api-key").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitKey();
      }
    });
  }

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
  const humanBox = $("#human-slot");
  const humanWidget = humanBox && window.RAYAN && window.RAYAN.human
    ? window.RAYAN.human.mount(humanBox, { onState: (st) => { if (st.ready) errorEl.textContent = ""; } })
    : null;

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
      fail(err.message);
      submit.disabled = false;
      label.textContent = original;
      // اثبات مصرف‌شده است؛ برای تلاش بعدی چالش تازه لازم است
      if (humanWidget) humanWidget.reset();
    }
  });

  if (window.RAYAN.config && window.RAYAN.config.offline) {
    fail("این صفحه در حالت استاتیک باز شده است؛ برای ورود، سرور را اجرا کن.");
  }

  checkExisting();
})();
