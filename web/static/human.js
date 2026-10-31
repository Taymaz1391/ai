/* رایان — «من ربات نیستم» بدون سرویس بیرونی.
 *
 * سرور یک نمک امضاشده و تعداد بیت می‌دهد؛ مرورگر باید عددی پیدا کند که
 * SHA-256("نمک:عدد") با همان تعداد بیت صفر شروع شود. برای آدم کسری از ثانیه
 * طول می‌کشد، برای رباتی که هزاران حساب می‌سازد گران است. هیچ درخواستی به
 * سرویس بیرونی نمی‌رود و هیچ تصویری هم لازم نیست.
 */
(function () {
  "use strict";

  /* ---------------------------------------------------------------- SHA-256 */
  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]);
  const rotr = (x, n) => (x >>> n) | (x << (32 - n));

  function hashBlock(H, W) {
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >>> 3);
      const s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >>> 10);
      W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let i = 0; i < 64; i++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + K[i] + W[i]) >>> 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0;
      d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0;
    H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0;
    H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
  }

  function sha256Hex(text) {
    const bytes = new TextEncoder().encode(text);
    const len = bytes.length;
    const blocks = Math.ceil((len + 9) / 64);
    const buf = new Uint8Array(blocks * 64);
    buf.set(bytes);
    buf[len] = 0x80;
    const bits = len * 8;
    const dv = new DataView(buf.buffer);
    dv.setUint32(buf.length - 4, bits >>> 0, false);
    dv.setUint32(buf.length - 8, Math.floor(bits / 0x100000000), false);
    const H = new Uint32Array([
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ]);
    const W = new Uint32Array(64);
    for (let off = 0; off < buf.length; off += 64) {
      for (let i = 0; i < 16; i++) W[i] = dv.getUint32(off + i * 4, false);
      hashBlock(H, W);
    }
    let out = "";
    for (let i = 0; i < 8; i++) out += H[i].toString(16).padStart(8, "0");
    return out;
  }

  function leadingZeroBits(hex, bits) {
    const full = bits >> 2;            // رقم‌های هگز کاملاً صفر
    for (let i = 0; i < full; i++) if (hex[i] !== "0") return false;
    const rem = bits % 4;
    if (!rem) return true;
    const nibble = parseInt(hex[full] || "0", 16);
    return (nibble >> (4 - rem)) === 0;
  }

  function bruteForce(salt, bits, onProgress, deadline) {
    for (let n = 0; n < 4_000_000; n++) {
      if (leadingZeroBits(sha256Hex(salt + ":" + n), bits)) return String(n);
      if ((n & 8191) === 0) {
        if (onProgress) onProgress(n);
        if (deadline && Date.now() > deadline) return null;
      }
    }
    return null;
  }

  /* --------------------------------------------------------------- حل تعاملی */
  function solveAsync(salt, bits, ui) {
    // قطعه‌قطعه حل می‌کنیم تا رابط کاربری قفل نشود
    return new Promise((resolve, reject) => {
      let n = 0;
      const step = () => {
        const started = Date.now();
        while (Date.now() - started < 24) {
          for (let i = 0; i < 400; i++, n++) {
            if (leadingZeroBits(sha256Hex(salt + ":" + n), bits)) {
              resolve(String(n));
              return;
            }
          }
          if (n > 6_000_000) {
            reject(new Error("چالش خیلی سنگین است؛ دوباره تلاش کنید."));
            return;
          }
        }
        if (ui) ui(n);
        setTimeout(step, 0);
      };
      step();
    });
  }

  /* ---------------------------------------------------------------- ویجت */
  function mount(box, options) {
    const opts = Object.assign({ name: "captcha", onState: null }, options || {});
    const state = { token: null, nonce: null, ready: false, busy: false, error: "" };
    box.innerHTML = "";
    box.classList.add("human-check");

    const row = document.createElement("label");
    row.className = "human-row";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.className = "human-box";
    input.setAttribute("aria-label", "من ربات نیستم");
    const text = document.createElement("span");
    text.className = "human-text";
    text.textContent = "من ربات نیستم";
    const badge = document.createElement("span");
    badge.className = "human-badge";
    badge.textContent = "بررسی امن، بدون سرویس بیرونی";
    row.append(input, text, badge);

    const note = document.createElement("div");
    note.className = "human-note";
    note.setAttribute("role", "status");
    note.setAttribute("aria-live", "polite");

    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = opts.name;

    box.append(row, note, hidden);

    const emit = () => {
      hidden.value = state.ready ? `${state.token}|${state.nonce}` : "";
      if (opts.onState) opts.onState(Object.assign({}, state));
    };

    function setNote(kind, message) {
      note.className = `human-note is-${kind}`;
      note.textContent = message || "";
    }

    async function start() {
      if (state.busy || state.ready) return;
      state.busy = true;
      input.disabled = true;
      setNote("busy", "در حال بررسی…");
      try {
        const res = await fetch(`${(window.RAYAN_CONFIG || {}).apiBase || ""}/api/captcha`, {
          headers: { accept: "application/json" },
          credentials: "same-origin",
        });
        if (!res.ok) throw new Error("چالش دریافت نشد");
        const ch = await res.json();
        setNote("busy", "یک لحظه… در حال تأیید انسان بودن");
        const nonce = await solveAsync(ch.salt, ch.bits, (n) => {
          if (n % 8000 < 400) setNote("busy", "در حال تأیید انسان بودن…");
        });
        if (nonce === null) throw new Error("حل نشد");
        state.token = ch.token;
        state.nonce = nonce;
        state.ready = true;
        state.error = "";
        input.checked = true;
        input.disabled = false;
        row.classList.add("is-verified");
        badge.textContent = "تأیید شد";
        setNote("ok", "انسان تأیید شد.");
      } catch (err) {
        state.ready = false;
        state.error = err && err.message ? err.message : "خطا";
        input.checked = false;
        input.disabled = false;
        row.classList.remove("is-verified");
        setNote("error", "بررسی ناموفق بود؛ دوباره بزنید.");
      } finally {
        state.busy = false;
        emit();
      }
    }

    input.addEventListener("change", () => {
      if (input.checked) start();
      else {
        state.ready = false;
        state.token = null;
        state.nonce = null;
        row.classList.remove("is-verified");
        badge.textContent = "بررسی امن، بدون سرویس بیرونی";
        setNote("", "");
        emit();
      }
    });

    emit();
    return {
      get value() {
        return state.ready ? { token: state.token, nonce: state.nonce } : null;
      },
      get ready() {
        return state.ready;
      },
      reset() {
        state.ready = false;
        state.token = null;
        state.nonce = null;
        input.checked = false;
        row.classList.remove("is-verified");
        setNote("", "");
        emit();
      },
      mount,
      solveAsync,
      sha256Hex,
      leadingZeroBits,
    };
  }

  window.RAYAN = window.RAYAN || {};
  window.RAYAN.human = { mount, solveAsync, sha256Hex, leadingZeroBits, bruteForce };
})();
