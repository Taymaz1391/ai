/* رایان — جای‌گذاری اعداد واقعی مدل در متن صفحه‌ها
   هیچ عددی در HTML دستی نوشته نمی‌شود: هر عنصر با data-model-slot از /api/model پر می‌شود. */
(function () {
  "use strict";

  const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
  const toFa = (text) => String(text).replace(/\d/g, (d) => FA_DIGITS[Number(d)]);
  const numerify = (value, digits) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return toFa(Number(value).toLocaleString("en-US", {
      minimumFractionDigits: digits || 0,
      maximumFractionDigits: digits || 0,
    }));
  };

  function valuesFrom(data) {
    const card = data || {};
    const run = card.run || {};
    const cfg = card.config || {};
    const params = card.params || run.params || 0;
    const layers = cfg.n_layer || run.layers;
    const heads = cfg.n_head || run.heads;
    const embed = cfg.n_embd || run.embed;
    const vocab = cfg.vocab_size || run.vocab;
    const tokens = run.tokens_seen;
    const bpc = run.bits_per_char;
    const valLoss = run.val_loss;
    const steps = run.steps;
    return {
      params: numerify(params, 0),
      "params-m": numerify(params / 1e6, 2),
      "params-long": params ? `${numerify(params / 1e6, 1)} میلیون` : "—",
      params_raw: String(params || ""),
      layers: numerify(layers, 0),
      heads: numerify(heads, 0),
      embed: numerify(embed, 0),
      vocab: numerify(vocab, 0),
      tokens: tokens ? `${numerify(tokens / 1e6, 1)} میلیون` : "—",
      tokens_raw: numerify(tokens, 0),
      steps: numerify(steps, 0),
      "val-loss": numerify(valLoss, 2),
      bpc: numerify(bpc, 3),
      ppl: numerify(run.ppl, 1),
      context: numerify(cfg.block_size || run.block_size, 0),
      speed: run.inference_tokens_per_second ? numerify(run.inference_tokens_per_second, 0) : "—",
      name: card.name || "رایان",
      "layers-heads": layers && heads ? `${numerify(layers, 0)} لایه و ${numerify(heads, 0)} سر` : "—",
    };
  }

  function apply(values) {
    document.querySelectorAll("[data-model-slot]").forEach((el) => {
      const key = el.getAttribute("data-model-slot");
      if (Object.prototype.hasOwnProperty.call(values, key)) {
        el.textContent = values[key];
      }
    });
  }

  async function load() {
    try {
      const response = await fetch("/api/model", { headers: { accept: "application/json" } });
      if (!response.ok) return;
      const data = await response.json();
      apply(valuesFrom(data));
      window.RAYAN_MODEL = data;
    } catch {
      /* بدون شبکه، متن پیش‌فرض می‌ماند */
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
  window.RAYAN_MODEL_SLOTS = { apply, valuesFrom };
})();
