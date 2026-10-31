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


  // ------------------------------------------------ ویدیوی معرفی پس از ثبت‌نام
  function playWelcomeReel(next) {
    const reel = $("#welcome-reel");
    const vid = $("#welcome-video");
    const skip = $("#welcome-skip");
    const sound = $("#welcome-sound");
    const close = $("#welcome-close");
    const full = $("#welcome-full");
    const progress = $("#welcome-progress");
    const hooks = [...document.querySelectorAll(".reel-hook")];
    if (!reel || !vid || !isSignup) {
      location.replace(next);
      return;
    }
    let done = false;
    const go = () => {
      if (done) return;
      done = true;
      try { vid.pause(); } catch { /* نادیده */ }
      try { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); } catch { /* نادیده */ }
      location.replace(next);
    };
    reel.hidden = false;
    document.body.classList.add("reel-open");
    // نسخهٔ عمودی برای گوشی، افقی برای دسکتاپ
    const vertical = window.matchMedia("(max-width: 760px)").matches;
    const src = vertical
      ? "/static/assets/video/promo-fa-9x16.mp4"
      : "/static/assets/video/promo-fa-16x9.mp4";
    const source = vid.querySelector("source");
    if (source) source.setAttribute("src", src);
    vid.setAttribute("poster", vertical
      ? "/static/assets/video/promo-fa-9x16-poster.jpg"
      : "/static/assets/video/promo-fa-16x9-poster.jpg");
    vid.load();
    if (skip) {
      skip.setAttribute("href", next);
      skip.addEventListener("click", (event) => {
        event.preventDefault();
        go();
      });
    }
    vid.addEventListener("ended", go, { once: true });
    vid.addEventListener("error", go, { once: true });
    // نوار پیشرفت و جمله‌های راهنما هم‌گام با پخش
    vid.addEventListener("timeupdate", () => {
      if (progress && vid.duration) {
        progress.style.width = `${Math.min(100, (vid.currentTime / vid.duration) * 100).toFixed(1)}%`;
      }
      hooks.forEach((hook) => {
        const at = Number(hook.dataset.at || 0);
        hook.classList.toggle("is-on", vid.currentTime >= at && vid.currentTime < at + 3.4);
      });
    });
    // ورود با کلید Escape یا ضربهٔ دوباره؛ خروج همیشه به گفتگو می‌رسد
    close?.addEventListener("click", go);

    // تمام‌صفحهٔ واقعی؛ اگر مرورگر اجازه نداد، همان پوشش کامل صفحه کافی است
    if (full) {
      full.addEventListener("click", async () => {
        try {
          if (document.fullscreenElement) {
            await document.exitFullscreen();
          } else {
            await (reel.requestFullscreen?.({ navigationUI: "hide" }) || reel.webkitRequestFullscreen?.());
          }
        } catch { /* نادیده */ }
      });
      document.addEventListener("fullscreenchange", () => {
        full.setAttribute("aria-pressed", document.fullscreenElement ? "true" : "false");
        full.textContent = document.fullscreenElement ? "خروج از تمام‌صفحه" : "تمام‌صفحه";
      });
    }
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") go();
    }, { once: true });
    // صدا روشن؛ اگر مرورگر اجازه نداد، بی‌صدا پخش می‌شود و دکمه صدا روشن می‌ماند
    const setSoundLabel = () => {
      if (!sound) return;
      sound.setAttribute("aria-pressed", vid.muted ? "false" : "true");
      sound.textContent = vid.muted ? "صدا" : "بی‌صدا";
    };
    vid.muted = false;
    const attempt = vid.play();
    if (attempt && typeof attempt.then === "function") {
      attempt.then(setSoundLabel).catch(() => {
        vid.muted = true;
        setSoundLabel();
        vid.play().catch(go);
      });
    } else {
      setSoundLabel();
    }
    if (skip) skip.focus({ preventScroll: true });
    // روی موبایل، چرخش صفحه نباید ویدیو را نصفه بگذارد
    const lock = () => {
      try { screen.orientation?.lock?.("portrait").catch(() => {}); } catch { /* نادیده */ }
    };
    if (vertical) lock();
    if (sound) {
      setSoundLabel();
      sound.addEventListener("click", () => {
        vid.muted = !vid.muted;
        setSoundLabel();
        if (!vid.muted) vid.play().catch(() => {});
      });
    }
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
