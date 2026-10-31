/* رایان — پخش خودکار ویدیوی تبلیغاتی + پیشنهاد زبان بر اساس IP/مرورگر */
(function () {
  "use strict";

  const video = document.getElementById("promo-video");
  const soundBtn = document.getElementById("promo-sound");
  const note = document.getElementById("promo-note");

  function isPortrait() {
    return window.matchMedia("(max-width: 760px)").matches;
  }

  function safePlay(el) {
    try {
      const p = el.play();
      if (p && typeof p.catch === "function") {
        p.catch(function () { onAutoplayBlocked(el); });
      }
    } catch (err) {
      onAutoplayBlocked(el);
    }
  }

  function onAutoplayBlocked(el) {
    el.removeAttribute("autoplay");
    if (note) {
      note.hidden = false;
      note.textContent = say(
        "مرورگر پخش خودکار را مسدود کرد؛ روی ویدیو بزن تا پخش شود.",
        "Your browser blocked autoplay — tap the video to start it."
      );
    }
  }

  function pageLang() {
    return (document.documentElement.lang || "fa").slice(0, 2).toLowerCase();
  }

  function isEnglish() {
    return pageLang() === "en";
  }

  function say(fa, en) {
    return isEnglish() ? en : fa;
  }

  async function locale() {
    try {
      let tz = "";
      try {
        tz = (Intl.DateTimeFormat().resolvedOptions().timeZone || "");
      } catch (err) { /* مرورگر قدیمی */ }
      const url = "/api/locale" + (tz ? "?tz=" + encodeURIComponent(tz) : "");
      const res = await fetch(url, { headers: { accept: "application/json" } });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  function showLangBanner(info) {
    if (!info || info.source === "query" || info.source === "cookie") return;
    if (info.lang === pageLang()) return;
    if (sessionStorage.getItem("rayan.lang.dismissed") === "1") return;
    const bar = document.createElement("div");
    bar.className = "lang-banner";
    bar.setAttribute("role", "status");
    const target = info.lang === "en" ? "/en?lang=en" : "/?lang=fa";
    const label = info.lang === "en"
      ? "This site is available in English."
      : "نسخهٔ فارسی سایت موجود است.";
    const cta = info.lang === "en" ? "Switch to English" : "رفتن به فارسی";
    const close = info.lang === "en" ? "Dismiss" : "بستن";
    bar.innerHTML =
      '<b>' + label + '</b>' +
      '<span class="lb-actions"><a class="btn btn-primary btn-sm" href="' + target + '">' + cta + '</a>' +
      '<button class="btn btn-ghost btn-sm" type="button" data-lb-close>' + close + '</button></span>';
    document.body.appendChild(bar);
    bar.querySelector("[data-lb-close]").addEventListener("click", function () {
      sessionStorage.setItem("rayan.lang.dismissed", "1");
      bar.remove();
    });
  }

  function apply(info) {
    if (!video) return;
    const lang = pageLang() === "en" ? "en" : "fa";
    const variants = (info && info.videos) || {
      landscape: "/static/assets/video/promo-" + lang + "-16x9.mp4",
      vertical: "/static/assets/video/promo-" + lang + "-9x16.mp4",
      square: "/static/assets/video/promo-" + lang + "-1x1.mp4",
      poster: "/static/assets/video/promo-" + lang + "-poster.jpg",
    };
    const source = isPortrait() ? variants.vertical : variants.landscape;
    const current = video.querySelector("source");
    if (!current || current.getAttribute("src") !== source) {
      if (current) current.setAttribute("src", source);
      video.load();
    }
    if (variants.poster && video.getAttribute("poster") !== variants.poster) {
      video.setAttribute("poster", variants.poster);
    }
    // پخش خودکار فقط بی‌صدا مجاز است؛ اگر مرورگر اجازه داد ادامه می‌دهیم
    safePlay(video);
  }

  if (soundBtn && video) {
    soundBtn.addEventListener("click", function () {
      const on = soundBtn.getAttribute("aria-pressed") !== "true";
      soundBtn.setAttribute("aria-pressed", on ? "true" : "false");
      video.muted = !on;
      const label = soundBtn.querySelector("span");
      if (label) label.textContent = on ? say("بی‌صدا", "Sound off") : say("صدا", "Sound on");
      if (on) safePlay(video);
    });
  }

  // وقتی ویدیو از کادر خارج شد، برای صرفه‌جویی در باتری متوقف شود
  if (video && "IntersectionObserver" in window) {
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          safePlay(video);
        } else {
          video.pause();
        }
      });
    }, { threshold: 0.25 });
    io.observe(video);
  }

  if (video) {
    video.addEventListener("click", function () {
      if (video.paused) safePlay(video);
    });
    let lastPortrait = isPortrait();
    window.addEventListener("resize", function () {
      const portrait = isPortrait();
      if (portrait !== lastPortrait) {
        lastPortrait = portrait;
        locale().then(apply);
      }
    });
  }

  locale().then(function (info) {
    apply(info);
    showLangBanner(info);
  });
})();
