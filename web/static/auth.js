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
    if (!reel || !vid || !isSignup) {
      location.replace(next);
      return;
    }
    let done = false;
    const go = () => {
      if (done) return;
      done = true;
      try { vid.pause(); } catch { /* نادیده */ }
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
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") go();
    }, { once: true });
    // صدا روشن؛ اگر مرورگر اجازه نداد، بی‌صدا پخش می‌شود
    vid.muted = false;
    const attempt = vid.play();
    if (attempt && typeof attempt.catch === "function") {
      attempt.catch(() => {
        vid.muted = true;
        if (sound) sound.setAttribute("aria-pressed", "false");
        vid.play().catch(go);
      });
    }
    if (sound) {
      sound.addEventListener("click", () => {
        vid.muted = !vid.muted;
        sound.setAttribute("aria-pressed", vid.muted ? "false" : "true");
        sound.textContent = vid.muted ? "صدا" : "بی‌صدا";
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

    submit.disabled = true;
    const original = label.textContent;
    label.textContent = "لطفاً صبر کن…";
    try {
      const path = isSignup ? "/api/auth/register" : "/api/auth/login";
      const body = isSignup
        ? { name, email: identifier, password }
        : { identifier, password };
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
    }
  });

  if (window.RAYAN.config && window.RAYAN.config.offline) {
    fail("این صفحه در حالت استاتیک باز شده است؛ برای ورود، سرور را اجرا کن.");
  }

  checkExisting();
})();
