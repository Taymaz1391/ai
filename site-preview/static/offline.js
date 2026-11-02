/* رایان — صفحهٔ آفلاین: تلاش دوباره و بازگشت خودکار پس از وصل‌شدن */
(function () {
  var retry = document.getElementById("retry");
  if (retry) retry.addEventListener("click", function () { location.reload(); });
  addEventListener("online", function () { location.reload(); });
})();
