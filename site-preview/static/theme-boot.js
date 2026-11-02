/* رایان — قفل تم پیش از رندر: پیش‌فرض روشن، انتخاب کاربر از localStorage */
(function () {
  try {
    var saved = localStorage.getItem("rayan.theme");
    document.documentElement.dataset.theme = saved === "dark" ? "dark" : "light";
  } catch (e) {
    document.documentElement.dataset.theme = "light";
  }
})();
