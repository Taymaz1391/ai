/* رایان — نمایش گفتگوی اشتراکی (فقط خواندن) */
(function () {
  "use strict";
  const { $, request, nf } = window.RAYAN;
  const token = location.pathname.split("/").filter(Boolean).pop() || "";

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function render(list) {
    const holder = $("#share-messages");
    holder.innerHTML = "";
    if (!list.length) {
      holder.innerHTML = '<p class="muted center">این گفتگو خالی است.</p>';
      return;
    }
    list.forEach((msg) => {
      const row = document.createElement("div");
      row.className = `share-msg ${msg.role === "user" ? "user" : "bot"}`;
      const who = document.createElement("div");
      who.className = "who";
      if (msg.role === "user") {
        who.textContent = "ش";
      } else {
        const img = document.createElement("img");
        img.src = "static/assets/brand/orb-128.png";
        img.alt = "رایان";
        img.width = 30;
        img.height = 30;
        who.append(img);
      }
      const content = document.createElement("div");
      content.className = "content";
      content.textContent = msg.content;
      row.append(who, content);
      holder.append(row);
    });
  }

  async function init() {
    try {
      const data = await request(`/api/share/${encodeURIComponent(token)}`);
      const conv = data.conversation || {};
      document.title = `${conv.title || "گفتگوی اشتراکی"} · رایان`;
      $("#share-title").textContent = conv.title || "گفتگوی اشتراکی";
      const date = conv.created_at ? new Date(conv.created_at * 1000).toLocaleDateString("fa-IR") : "—";
      $("#share-date").textContent = date;
      $("#share-views").textContent = `${nf(conv.views || 0)} بازدید`;
      render(conv.messages || []);
      $("#share-cta").hidden = false;
    } catch (err) {
      $("#share-messages").innerHTML = `
        <div class="form-alert">${escapeHtml(err.message)}</div>
        <p class="muted" style="margin-top:16px">ممکن است صاحب گفتگو اشتراک را لغو کرده باشد.</p>`;
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
