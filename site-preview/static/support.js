/* رایان — فرم پشتیبانی تجاری. */
(function () {
  "use strict";

  const R = window.RAYAN;
  const $ = (sel) => document.querySelector(sel);
  const form = $("#support-form");
  const errorEl = $("#support-error");
  const okEl = $("#support-ok");
  const submit = $("#support-submit");

  function setPlan(plan) {
    const select = $("#sup-plan");
    if (select && plan) select.value = plan;
    form?.scrollIntoView({ behavior: "smooth", block: "center" });
    $("#sup-email")?.focus({ preventScroll: true });
  }

  document.querySelectorAll(".support-pick").forEach((btn) => {
    btn.addEventListener("click", () => setPlan(btn.dataset.plan));
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.textContent = "";
    okEl.textContent = "";
    const payload = {
      name: $("#sup-name").value.trim(),
      email: $("#sup-email").value.trim(),
      plan: $("#sup-plan").value,
      topic: $("#sup-topic").value.trim(),
      message: $("#sup-message").value.trim(),
    };
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(payload.email)) {
      errorEl.textContent = "ایمیل معتبر لازم است.";
      return;
    }
    if (payload.message.length < 10) {
      errorEl.textContent = "پیام خیلی کوتاه است؛ کمی بیشتر توضیح بده.";
      return;
    }
    submit.disabled = true;
    const label = submit.textContent;
    submit.textContent = "در حال ارسال…";
    try {
      const data = await R.request("/api/support", { method: "POST", body: payload });
      okEl.textContent = data.note || "ثبت شد.";
      form.reset();
      R.toast("درخواست پشتیبانی ثبت شد.", "ok");
    } catch (err) {
      errorEl.textContent = err.message;
    } finally {
      submit.disabled = false;
      submit.textContent = label;
    }
  });
})();
