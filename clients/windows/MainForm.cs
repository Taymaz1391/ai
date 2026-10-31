using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Rayan;

/// <summary>
/// پوستهٔ نازک ویندوز. هیچ منطق دسترسی یا سهمیه‌ای این‌جا نیست؛
/// ورود، نقش مدیر و مصرف همه سمت سرور بررسی می‌شوند و کاربر نمی‌تواند
/// با دست‌کاری کلاینت خودش را آنلاین یا ویژه نشان دهد.
/// </summary>
public sealed class MainForm : Form
{
    private static readonly string ServerUrl =
        Environment.GetEnvironmentVariable("RAYAN_SERVER_URL") is { Length: > 0 } custom
            ? custom.TrimEnd('/')
            : BuildInfo.ServerUrl.TrimEnd('/');

    private static readonly Uri ServerUri = new(ServerUrl);
    private readonly WebView2 _web = new();
    private readonly Panel _error = new();
    private readonly Label _status = new();

    public MainForm()
    {
        Text = "رایان — هوش مصنوعی به زبان فارسی";
        MinimumSize = new Size(420, 560);
        Size = new Size(1180, 800);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(247, 250, 255);
        RightToLeft = RightToLeft.Yes;
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);

        _web.Dock = DockStyle.Fill;
        Controls.Add(_web);
        BuildErrorPanel();
        Load += async (_, _) => await InitAsync();
        KeyPreview = true;
        KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.F5) { e.Handled = true; _web.Reload(); }
        };
    }

    private void BuildErrorPanel()
    {
        _error.Dock = DockStyle.Fill;
        _error.BackColor = Color.FromArgb(247, 250, 255);
        _error.Visible = false;

        _status.Text = "اتصال به سرور برقرار نشد.\nرایان همهٔ پاسخ‌ها را از سرور می‌گیرد؛ اینترنت یا نشانی سرور را بررسی کن.";
        _status.AutoSize = false;
        _status.Dock = DockStyle.Top;
        _status.Height = 90;
        _status.TextAlign = ContentAlignment.MiddleCenter;
        _status.Font = new Font("Segoe UI", 11F);
        _status.ForeColor = Color.FromArgb(63, 80, 105);

        var retry = new Button
        {
            Text = "تلاش دوباره",
            AutoSize = true,
            BackColor = Color.FromArgb(26, 92, 224),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            Padding = new Padding(18, 6, 18, 6),
        };
        retry.Click += (_, _) =>
        {
            _error.Visible = false;
            _web.Visible = true;
            _ = _web.EnsureCoreWebView2Async();
        };

        var host = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
            Padding = new Padding(28),
        };
        host.Controls.Add(_status);
        host.Controls.Add(retry);
        _error.Controls.Add(host);
        Controls.Add(_error);
        _error.BringToFront();
    }

    private async System.Threading.Tasks.Task InitAsync()
    {
        try
        {
            var dataDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "Rayan", "WebView2");
            Directory.CreateDirectory(dataDir);

            var env = await CoreWebView2Environment.CreateAsync(null, dataDir);
            await _web.EnsureCoreWebView2Async(env);

            var core = _web.CoreWebView2;
            var settings = core.Settings;
            settings.AreDevToolsEnabled = false;
            settings.AreBrowserAcceleratorKeysEnabled = false;
            settings.IsStatusBarEnabled = false;
            settings.AreDefaultScriptDialogsEnabled = true;
            settings.IsPasswordAutosaveEnabled = true;
            settings.UserAgent = settings.UserAgent + " RayanWin/6.0";

            core.NewWindowRequested += (_, e) =>
            {
                e.Handled = true;
                OpenExternal(e.Uri);
            };

            core.NavigationStarting += (_, e) =>
            {
                if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var target)) return;
                if (target.Scheme is "https" or "http" &&
                    !string.Equals(target.Host, ServerUri.Host, StringComparison.OrdinalIgnoreCase))
                {
                    e.Cancel = true;
                    OpenExternal(e.Uri);
                }
            };

            core.NavigationCompleted += (_, e) =>
            {
                if (!e.IsSuccess)
                {
                    _web.Visible = false;
                    _error.Visible = true;
                    _error.BringToFront();
                }
                else
                {
                    _error.Visible = false;
                    _web.Visible = true;
                }
            };

            core.Navigate(ServerUrl);
        }
        catch (Exception ex)
        {
            _status.Text = "WebView2 در دسترس نیست.\n" +
                           "اجرای Microsoft Edge WebView2 Runtime لازم است (روی ویندوز ۱۱ از پیش نصب است).\n" +
                           ex.Message;
            _web.Visible = false;
            _error.Visible = true;
            _error.BringToFront();
        }
    }

    private static void OpenExternal(string uri)
    {
        try
        {
            Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
        }
        catch
        {
            // نادیده: باز نشدن مرورگر نباید برنامه را ببندد
        }
    }
}
