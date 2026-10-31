namespace Rayan;

/// <summary>
/// نشانی سرور در زمان ساخت داخل برنامه قرار می‌گیرد.
/// CI این فایل را با نشانی واقعی استقرار بازنویسی می‌کند
/// (متغیر مخزن <c>RAYAN_SERVER_URL</c>).
/// </summary>
internal static class BuildInfo
{
    internal const string ServerUrl = "https://rayan.example";
}
