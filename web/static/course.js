/* رایان — دورهٔ ۵ ساعته: پیشرفت، خواندن با صدا و پیمایش */
(function () {
  "use strict";

  var KEY = "rayan.course.v1";
  var lessons = Array.prototype.slice.call(document.querySelectorAll("[data-lesson]"));
  var bar = document.getElementById("course-bar-fill");
  var percent = document.getElementById("course-percent");
  var counter = document.getElementById("course-done-label");
  var resume = document.getElementById("course-resume");
  var reset = document.getElementById("course-reset");
  var print = document.getElementById("course-print");
  var faDigits = function (value) {
    return String(value).replace(/\d/g, function (d) {
      return "۰۱۲۳۴۵۶۷۸۹"[Number(d)];
    });
  };

  function read() {
    try {
      var raw = localStorage.getItem(KEY);
      var data = raw ? JSON.parse(raw) : null;
      if (data && Array.isArray(data.done)) return data;
    } catch (err) { /* حافظه در دسترس نیست */ }
    return { done: [] };
  }

  function write(data) {
    try { localStorage.setItem(KEY, JSON.stringify(data)); } catch (err) { /* بی‌صدا */ }
  }

  function totalMinutes() {
    return lessons.reduce(function (sum, el) {
      return sum + (Number(el.getAttribute("data-min")) || 0);
    }, 0);
  }

  function paint() {
    var data = read();
    var done = data.done.filter(function (id) {
      return lessons.some(function (el) { return el.getAttribute("data-lesson") === id; });
    });
    var pct = lessons.length ? Math.round((done.length / lessons.length) * 100) : 0;
    lessons.forEach(function (el) {
      var id = el.getAttribute("data-lesson");
      var isDone = done.indexOf(id) !== -1;
      el.classList.toggle("is-done", isDone);
      var btn = el.querySelector("[data-done]");
      if (btn) {
        btn.setAttribute("aria-pressed", isDone ? "true" : "false");
        btn.textContent = isDone ? "خوانده شد ✓" : "خواندم";
      }
    });
    if (bar) bar.style.width = pct + "%";
    if (percent) percent.textContent = faDigits(pct) + "٪";
    if (counter) {
      var mins = lessons.reduce(function (sum, el) {
        return sum + (read().done.indexOf(el.getAttribute("data-lesson")) !== -1
          ? (Number(el.getAttribute("data-min")) || 0) : 0);
      }, 0);
      counter.textContent = faDigits(done.length) + " از " + faDigits(lessons.length) +
        " درس · " + faDigits(mins) + " از " + faDigits(totalMinutes()) + " دقیقه";
    }
  }

  function toggle(id) {
    var data = read();
    var idx = data.done.indexOf(id);
    if (idx === -1) data.done.push(id);
    else data.done.splice(idx, 1);
    write(data);
    paint();
  }

  lessons.forEach(function (el) {
    var btn = el.querySelector("[data-done]");
    if (btn) {
      btn.addEventListener("click", function () {
        toggle(el.getAttribute("data-lesson"));
      });
    }
  });

  if (resume) {
    resume.addEventListener("click", function () {
      var data = read();
      var next = lessons.filter(function (el) {
        return data.done.indexOf(el.getAttribute("data-lesson")) === -1;
      })[0];
      if (!next) {
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      next.open = true;
      next.scrollIntoView({ behavior: "smooth", block: "start" });
      var mark = next.querySelector("[data-done]");
      if (mark) mark.focus({ preventScroll: true });
    });
  }

  if (reset) {
    reset.addEventListener("click", function () {
      if (!window.confirm("پیشرفت دوره پاک شود؟")) return;
      write({ done: [] });
      paint();
    });
  }

  if (print) {
    print.addEventListener("click", function () { window.print(); });
  }

  // ---------------------------------------------------------- خواندن با صدا
  var speaking = null;

  function stopSpeaking() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    document.querySelectorAll("[data-read]").forEach(function (b) {
      b.setAttribute("aria-pressed", "false");
      b.textContent = "خواندن با صدا";
    });
    speaking = null;
  }

  function speak(article, button) {
    if (!("speechSynthesis" in window)) {
      button.disabled = true;
      button.textContent = "مرورگر پشتیبانی نمی‌کند";
      return;
    }
    if (speaking === article) { stopSpeaking(); return; }
    stopSpeaking();
    var text = (article.querySelector(".lesson-text") || article).innerText
      .replace(/\s+/g, " ")
      .trim();
    if (!text) return;
    var parts = [];
    var rest = text;
    while (rest.length > 180) {
      var cut = rest.lastIndexOf(" ", 180);
      if (cut < 60) cut = 180;
      parts.push(rest.slice(0, cut));
      rest = rest.slice(cut + 1);
    }
    if (rest) parts.push(rest);
    speaking = article;
    button.setAttribute("aria-pressed", "true");
    button.textContent = "توقف";
    parts.forEach(function (part, index) {
      var utter = new SpeechSynthesisUtterance(part);
      utter.lang = "fa-IR";
      utter.rate = 0.98;
      utter.pitch = 1;
      if (index === parts.length - 1) {
        utter.onend = function () {
          if (speaking === article) stopSpeaking();
        };
      }
      utter.onerror = function () {
        if (speaking === article) stopSpeaking();
      };
      window.speechSynthesis.speak(utter);
    });
  }

  document.querySelectorAll("[data-read]").forEach(function (button) {
    button.addEventListener("click", function () {
      var article = document.getElementById(button.getAttribute("data-read"));
      if (article) speak(article, button);
    });
  });

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stopSpeaking();
  });

  // ---------------------------------------------------------- فهرست چسبان
  if ("IntersectionObserver" in window) {
    var links = {};
    document.querySelectorAll(".course-toc a[href^='#']").forEach(function (a) {
      links[a.getAttribute("href").slice(1)] = a;
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var link = links[entry.target.id];
        if (!link || !entry.isIntersecting) return;
        Object.keys(links).forEach(function (key) { links[key].classList.remove("is-active"); });
        link.classList.add("is-active");
      });
    }, { rootMargin: "-20% 0px -70% 0px" });
    lessons.forEach(function (el) { io.observe(el); });
  }

  paint();
})();
