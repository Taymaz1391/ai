/* رایان — گفتگوی صوتی، کاملاً در مرورگر.
 *
 * ورودی با SpeechRecognition (فارسی) و خروجی با speechSynthesis انجام می‌شود؛
 * هیچ صدا یا متنی به سرویس بیرونی نمی‌رود و هیچ کلیدی لازم نیست. اگر مرورگر
 * این دو را نداشته باشد، دکمه غیرفعال می‌شود و راهنمای کوتاه نشان داده می‌شود.
 *
 * چرخه: گوش می‌دهد → متن را در کادر می‌نویسد → می‌فرستد → پاسخ را می‌خواند →
 * اگر «دست‌آزاد» روشن باشد دوباره گوش می‌دهد.
 */
(function () {
  "use strict";

  const btn = document.getElementById("voice-btn");
  if (!btn) return;

  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const synth = window.speechSynthesis;
  const supported = !!Recognition && !!synth;

  const state = {
    listening: false,
    speaking: false,
    handsFree: false,
    lang: "fa-IR",
    voice: null,
    rec: null,
    finalText: "",
    lastError: "",
  };

  function setPressed() {
    btn.setAttribute("aria-pressed", state.listening ? "true" : "false");
    btn.classList.toggle("is-listening", state.listening);
    btn.classList.toggle("is-speaking", state.speaking);
    const label = btn.querySelector(".voice-label");
    if (label) label.textContent = state.listening ? "گوش می‌دهم" : state.speaking ? "می‌خوانم" : "صوتی";
    const hint = document.getElementById("composer-hint");
    if (hint && state.listening) hint.textContent = "صاف و شمرده بگو…";
    else if (hint && state.speaking) hint.textContent = "در حال خواندن پاسخ…";
    else if (hint && !state.listening && !state.speaking) hint.textContent = "";
  }

  function pickVoice() {
    if (!synth) return null;
    const voices = synth.getVoices() || [];
    const fa = voices.filter((v) => /fa[-_]?IR|persian|فارسی/i.test(`${v.lang} ${v.name}`));
    if (fa.length) return fa[0];
    return voices.find((v) => v.default) || voices[0] || null;
  }

  if (synth) {
    const refresh = () => { state.voice = pickVoice(); };
    refresh();
    synth.addEventListener?.("voiceschanged", refresh);
    synth.onvoiceschanged = refresh;
  }

  function speak(text) {
    if (!synth || !text) return;
    const clean = String(text)
      .replace(/```[\s\S]*?```/g, " ")
      .replace(/[*_`>#]/g, "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 1200);
    if (!clean) return;
    synth.cancel();
    const utter = new SpeechSynthesisUtterance(clean);
    utter.lang = state.lang;
    if (!state.voice) state.voice = pickVoice();
    if (state.voice) utter.voice = state.voice;
    utter.rate = 1.02;
    utter.pitch = 1;
    utter.onstart = () => { state.speaking = true; setPressed(); };
    utter.onend = () => {
      state.speaking = false;
      setPressed();
      if (state.handsFree && !state.listening) setTimeout(() => start(), 350);
    };
    utter.onerror = () => { state.speaking = false; setPressed(); };
    synth.speak(utter);
  }

  function stopSpeaking() {
    if (synth) synth.cancel();
    state.speaking = false;
    setPressed();
  }

  function makeRecognizer() {
    const rec = new Recognition();
    rec.lang = state.lang;
    rec.continuous = false;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onstart = () => { state.listening = true; state.finalText = ""; setPressed(); };
    rec.onresult = (event) => {
      let interim = "";
      let final = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) final += result[0].transcript;
        else interim += result[0].transcript;
      }
      state.finalText = (state.finalText + " " + final).trim();
      const text = (state.finalText + " " + interim).trim();
      const prompt = document.getElementById("prompt");
      if (prompt && text) {
        prompt.value = text;
        prompt.dispatchEvent(new Event("input", { bubbles: true }));
      }
    };
    rec.onerror = (event) => {
      state.listening = false;
      state.lastError = event.error || "";
      if (state.lastError === "not-allowed" || state.lastError === "service-not-allowed") {
        window.RAYAN?.toast?.("دسترسی به میکروفون داده نشد؛ از تنظیمات مرورگر اجازه بده.", "error");
        state.handsFree = false;
      } else if (state.lastError === "no-speech") {
        window.RAYAN?.toast?.("صدایی نشنیدم؛ دوباره بزن.", "");
      }
      setPressed();
    };
    rec.onend = () => {
      state.listening = false;
      setPressed();
      const text = state.finalText.trim();
      if (text && window.RAYAN_CHAT) {
        window.RAYAN_CHAT.say(text);
      } else if (state.handsFree && !state.speaking) {
        setTimeout(() => start(), 400);
      }
    };
    return rec;
  }

  function start() {
    if (!supported) return;
    if (state.listening) { stop(); return; }
    stopSpeaking();
    try {
      state.rec = state.rec || makeRecognizer();
      state.rec.start();
    } catch {
      // شروع دوبارهٔ همان نمونه پیش از پایان، خطا می‌دهد؛ نمونهٔ تازه بساز
      state.rec = makeRecognizer();
      try { state.rec.start(); } catch { /* نادیده */ }
    }
  }

  function stop() {
    if (state.rec) {
      try { state.rec.stop(); } catch { /* نادیده */ }
    }
    state.listening = false;
    setPressed();
  }

  btn.addEventListener("click", () => {
    if (!supported) {
      window.RAYAN?.toast?.("مرورگر تو گفتگوی صوتی را پشتیبانی نمی‌کند؛ Chrome یا Edge را امتحان کن.", "error");
      return;
    }
    if (state.listening) stop();
    else start();
  });

  // دوبار کلیک: حالت دست‌آزاد
  btn.addEventListener("dblclick", (event) => {
    event.preventDefault();
    state.handsFree = !state.handsFree;
    window.RAYAN?.toast?.(state.handsFree
      ? "حالت دست‌آزاد روشن شد؛ بعد از هر پاسخ دوباره گوش می‌دهم."
      : "حالت دست‌آزاد خاموش شد.", "ok");
    btn.classList.toggle("is-hands-free", state.handsFree);
  });

  document.addEventListener("rayan:answer", (event) => {
    if (state.handsFree || state.listening || state.speaking) {
      const text = event.detail?.text || "";
      if (text) speak(text);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && (state.listening || state.speaking)) {
      stop();
      stopSpeaking();
    }
  });

  if (!supported) {
    btn.classList.add("is-unsupported");
    btn.title = "مرورگر تو گفتگوی صوتی را پشتیبانی نمی‌کند";
  }

  window.RAYAN_VOICE = {
    supported,
    start,
    stop,
    speak,
    stopSpeaking,
    get handsFree() { return state.handsFree; },
    set handsFree(value) { state.handsFree = !!value; btn.classList.toggle("is-hands-free", state.handsFree); },
  };
})();
