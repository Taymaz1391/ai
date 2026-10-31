/* رایان — صفحهٔ کلیدهای API: ساخت، فهرست و لغو. */
(function () {
  "use strict";

  const R = window.RAYAN;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const gate = $("#key-gate");
  const form = $("#key-form");
  const list = $("#key-list");
  const secretBox = $("#key-secret");
  const secretValue = $("#key-secret-value");

  const faDate = (epoch) => {
    if (!epoch) return "—";
    try {
      return new Date(epoch * 1000).toLocaleDateString("fa-IR", { day: "numeric", month: "long", year: "numeric" });
    } catch {
      return "—";
    }
  };

  function renderKeys(keys) {
    list.innerHTML = "";
    if (!keys.length) {
      const li = document.createElement("li");
      li.className = "key-empty";
      li.textContent = "هنوز کلیدی نساخته‌ای.";
      list.append(li);
      return;
    }
    for (const key of keys) {
      const li = document.createElement("li");
      li.className = `key-item${key.revoked_at ? " is-revoked" : ""}`;
      const main = document.createElement("div");
      main.className = "key-main";
      const title = document.createElement("b");
      title.textContent = key.name || "کلید بدون نام";
      const meta = document.createElement("span");
      meta.textContent = `${key.prefix}•••• · ساخت ${faDate(key.created_at)}` +
        (key.last_used ? ` · آخرین استفاده ${faDate(key.last_used)}` : " · استفاده‌نشده");
      main.append(title, meta);
      li.append(main);
      if (!key.revoked_at) {
        const btn = document.createElement("button");
        btn.className = "btn btn-sm";
        btn.type = "button";
        btn.textContent = "لغو";
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          try {
            await R.request(`/api/keys/${key.id}`, { method: "DELETE" });
            R.toast("کلید لغو شد.", "ok");
            await load();
          } catch (err) {
            R.toast(err.message, "error");
            btn.disabled = false;
          }
        });
        li.append(btn);
      }
      list.append(li);
    }
  }

  async function load() {
    try {
      const data = await R.request("/api/keys");
      gate.hidden = true;
      form.hidden = false;
      renderKeys(data.keys || []);
    } catch {
      gate.hidden = false;
      form.hidden = true;
    }
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("#key-name").value.trim();
    const btn = $("#key-submit");
    btn.disabled = true;
    try {
      const data = await R.request("/api/keys", { method: "POST", body: { name } });
      secretBox.hidden = false;
      secretValue.textContent = data.secret;
      R.toast("کلید ساخته شد؛ همین حالا کپی کن.", "ok");
      await load();
    } catch (err) {
      R.toast(err.message, "error");
    } finally {
      btn.disabled = false;
    }
  });

  $("#key-copy")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(secretValue.textContent);
      R.toast("کپی شد.", "ok");
    } catch {
      R.toast("کپی نشد؛ دستی انتخاب کن.", "error");
    }
  });

  $$(".faq-q").forEach((q) => {
    q.addEventListener("click", () => {
      const open = q.getAttribute("aria-expanded") === "true";
      q.setAttribute("aria-expanded", String(!open));
      q.parentElement.classList.toggle("is-open", !open);
    });
  });

  load();
})();
