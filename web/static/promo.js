/* رایان — پخش خودکار ویدیوی تبلیغاتی (فارسی، هر نسبت تصویر) */
(function () {
  "use strict";

  const video = document.getElementById("promo-video");
  const soundBtn = document.getElementById("promo-sound");
  const note = document.getElementById("promo-note");

  const VARIANTS = {
    landscape: "/static/assets/video/promo-fa-16x9.mp4",
    vertical: "/static/assets/video/promo-fa-9x16.mp4",
    square: "/static/assets/video/promo-fa-1x1.mp4",
    poster: "/static/assets/video/promo-fa-poster.jpg",
  };

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
      note.textContent = "مرورگر پخش خودکار را مسدود کرد؛ روی ویدیو بزن تا پخش شود.";
    }
  }

  function apply() {
    if (!video) return;
    const source = isPortrait() ? VARIANTS.vertical : VARIANTS.landscape;
    const current = video.querySelector("source");
    if (!current || current.getAttribute("src") !== source) {
      if (current) current.setAttribute("src", source);
      video.load();
    }
    if (video.getAttribute("poster") !== VARIANTS.poster) {
      video.setAttribute("poster", VARIANTS.poster);
    }
    // پخش خودکار فقط بی‌صدا مجاز است
    safePlay(video);
  }

  if (soundBtn && video) {
    soundBtn.addEventListener("click", function () {
      const on = soundBtn.getAttribute("aria-pressed") !== "true";
      soundBtn.setAttribute("aria-pressed", on ? "true" : "false");
      video.muted = !on;
      const label = soundBtn.querySelector("span");
      if (label) label.textContent = on ? "بی‌صدا" : "صدا";
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
        apply();
      }
    });
  }

  apply();
})();
