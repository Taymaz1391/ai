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
    private static readonly string SettingsDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Rayan");

    private readonly WebView2 _web = new();
    private readonly Panel _error = new();
    private readonly Label _status = new();
    private readonly TextBox _serverBox = new();

    private string _serverUrl = "";

    public MainForm()
    {
        Text = "رایان — هوش مصنوعی به زبان فارسی";
        MinimumSize = new Size(420, 560);
        Size = new Size(1180, 800);
        StartPosition = FormStartPosition.CenterScreen;
        BackColor = Color.FromArgb(247, 250, 255);
        RightToLeft = RightToLeft.Yes;
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);

        _serverUrl = ResolveServerUrl();

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

    private static string ResolveServerUrl()
    {
        try
        {
            var file = Path.Combine(SettingsDir, "server.txt");
            if (File.Exists(file))
            {
                var stored = File.ReadAllText(file).Trim();
                if (stored.Length > 0) return Normalise(stored);
            }
        }
        catch { /* نادیده */ }

        if (Environment.GetEnvironmentVariable("RAYAN_SERVER_URL") is { Length: > 0 } custom)
        {
            return Normalise(custom);
        }
        return Normalise(BuildInfo.ServerUrl);
    }

    private static string Normalise(string raw)
    {
        var value = (raw ?? "").Trim().TrimEnd('/');
        if (value.Length == 0) return "";
        if (!value.StartsWith("http://", StringComparison.OrdinalIgnoreCase) &&
            !value.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            value = "https://" + value;
        }
        return value;
    }

    private void BuildErrorPanel()
    {
        _error.Dock = DockStyle.Fill;
        _error.BackColor = Color.FromArgb(247, 250, 255);
        _error.Visible = false;

        _status.Text = "اتصال به سرور برقرار نشد.\nرایان همهٔ پاسخ‌ها را از سرور می‌گیرد؛ اینترنت یا نشانی سرور را بررسی کن.";
        _status.AutoSize = false;
        _status.Dock = DockStyle.Top;
        _status.Height = 78;
        _status.TextAlign = ContentAlignment.MiddleCenter;
        _status.Font = new Font("Segoe UI", 11F);
        _status.ForeColor = Color.FromArgb(63, 80, 105);

        _serverBox.Dock = DockStyle.Top;
        _serverBox.Height = 34;
        _serverBox.Text = _serverUrl.Contains("rayan.example", StringComparison.OrdinalIgnoreCase) ? "" : _serverUrl;
        _serverBox.PlaceholderText = "https://your-server.example";
        _serverBox.RightToLeft = RightToLeft.No;
        _serverBox.Margin = new Padding(0, 8, 0, 8);

        var retry = new Button
        {
            Text = "اتصال",
            AutoSize = true,
            BackColor = Color.FromArgb(26, 92, 224),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
            Padding = new Padding(18, 6, 18, 6),
            Margin = new Padding(0, 10, 0, 0),
        };
        retry.Click += async (_, _) =>
        {
            var value = Normalise(_serverBox.Text);
            if (value.Length == 0) return;
            _serverUrl = value;
            try
            {
                Directory.CreateDirectory(SettingsDir);
                File.WriteAllText(Path.Combine(SettingsDir, "server.txt"), value);
            }
            catch { /* نادیده */ }

            _error.Visible = false;
            _web.Visible = true;
            await InitAsync();
        };

        var host = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
            Padding = new Padding(28),
        };
        host.Controls.Add(_status);
        host.Controls.Add(_serverBox);
        host.Controls.Add(retry);
        _error.Controls.Add(host);
        Controls.Add(_error);
        _error.BringToFront();
    }

    private async System.Threading.Tasks.Task InitAsync()
    {
        try
        {
            if (_serverUrl.Length == 0 || _serverUrl.Contains("rayan.example", StringComparison.OrdinalIgnoreCase))
            {
                ShowError("برای شروع، نشانی سرور رایان را وارد کن.\nاین کلاینت به همان سرور وصل می‌شود؛ ورود و سهمیه همان‌جا بررسی می‌شود.");
                return;
            }

            var dataDir = Path.Combine(SettingsDir, "WebView2");
            Directory.CreateDirectory(dataDir);
            var env = await CoreWebView2Environment.CreateAsync(null, dataDir);
            await _web.EnsureCoreWebView2Async(env);

            var core = _web.CoreWebView2;
            var settings = core.Settings;
            settings.AreDevToolsEnabled = false;
            settings.AreBrowserAcceleratorKeysEnabled = false;
            settings.IsStatusBarEnabled = false;
            settings.IsPasswordAutosaveEnabled = true;
            settings.UserAgent = settings.UserAgent + " RayanWin/6.0";

            var serverHost = new Uri(_serverUrl).Host;
            core.NewWindowRequested += (_, e) =>
            {
                e.Handled = true;
                OpenExternal(e.Uri);
            };

            core.NavigationStarting += (_, e) =>
            {
                if (!Uri.TryCreate(e.Uri, UriKind.Absolute, out var target)) return;
                if (target.Scheme is "https" or "http" &&
                    !string.Equals(target.Host, serverHost, StringComparison.OrdinalIgnoreCase))
                {
                    e.Cancel = true;
                    OpenExternal(e.Uri);
                }
            };

            core.NavigationCompleted += (_, e) =>
            {
                if (!e.IsSuccess)
                {
                    ShowError("اتصال به سرور برقرار نشد.\nنشانی یا دسترس‌پذیری سرور را بررسی کن.");
                }
                else
                {
                    _error.Visible = false;
                    _web.Visible = true;
                }
            };

            _error.Visible = false;
            _web.Visible = true;
            core.Navigate(_serverUrl);
        }
        catch (Exception ex)
        {
            ShowError("WebView2 در دسترس نیست.\n" +
                      "اجرای Microsoft Edge WebView2 Runtime لازم است (روی ویندوز ۱۱ از پیش نصب است).\n" +
                      ex.Message);
        }
    }

    private void ShowError(string message)
    {
        _status.Text = message;
        _web.Visible = false;
        _error.Visible = true;
        _error.BringToFront();
    }

    private static void OpenExternal(string uri)
    {
        try
        {
            Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
        }
        catch
        {
            // باز نشدن مرورگر نباید برنامه را ببندد
        }
    }
}
