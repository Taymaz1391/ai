package ir.rayan.app;

import android.annotation.SuppressLint;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import android.app.Activity;
import android.content.SharedPreferences;
import android.widget.EditText;

/**
 * کلاینت نازک رایان.
 *
 * <p>هیچ تصمیم امنیتی یا سهمیه‌ای در این‌جا گرفته نمی‌شود: نشست، نقش مدیر و
 * سهمیهٔ مصرف همه سمت سرور تعیین می‌شوند. این پوسته فقط صفحهٔ همان سرور را
 * نمایش می‌دهد و اجازه نمی‌دهد کاربر با دست‌کاری کلاینت، «آنلاین» یا «ویژه»
 * جا بزند.</p>
 */
public class MainActivity extends Activity {

    private static final String PREFS = "rayan";
    private static final String KEY_SERVER = "server_url";

    private WebView web;
    private View errorView;
    private String serverUrl;
    private SharedPreferences prefs;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_main);
        web = findViewById(R.id.web);
        errorView = findViewById(R.id.error);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        serverUrl = normalise(prefs.getString(KEY_SERVER, "")).isEmpty()
            ? Config.SERVER_URL : normalise(prefs.getString(KEY_SERVER, ""));

        EditText field = findViewById(R.id.server_url);
        field.setText(serverUrl);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            Window window = getWindow();
            window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
            window.setStatusBarColor(Color.parseColor("#F7FAFF"));
        }

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setUserAgentString(s.getUserAgentString() + " RayanAndroid/" + Config.VERSION);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, false);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (uri.getHost() != null && uri.getHost().equals(host())) {
                    return false; // همان سرور: داخل برنامه
                }
                startActivity(new Intent(Intent.ACTION_VIEW, uri)); // بقیه: مرورگر
                return true;
            }

            @Override
            public void onReceivedError(WebView view, int code, String description, String failingUrl) {
                if (failingUrl != null && failingUrl.startsWith(serverUrl)) {
                    showError();
                }
            }
        });

        findViewById(R.id.retry).setOnClickListener(v -> connect());
        if (serverUrl.contains("rayan.example")) {
            serverUrl = "";
            showError();  // نصب تازه: نشانی سرور را از کاربر بگیر
            return;
        }
        web.loadUrl(serverUrl);
    }

    private void connect() {
        EditText field = findViewById(R.id.server_url);
        String value = normalise(field.getText().toString());
        if (value.isEmpty()) {
            showError();
            return;
        }
        serverUrl = value;
        prefs.edit().putString(KEY_SERVER, value).apply();
        errorView.setVisibility(View.GONE);
        web.setVisibility(View.VISIBLE);
        web.loadUrl(serverUrl);
    }

    private String host() {
        try {
            String h = Uri.parse(serverUrl).getHost();
            return h == null ? "" : h;
        } catch (Exception exc) {
            return "";
        }
    }

    private static String normalise(String raw) {
        String value = raw == null ? "" : raw.trim();
        if (value.isEmpty()) return "";
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "https://" + value;
        }
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }

    private void showError() {
        web.setVisibility(View.GONE);
        errorView.setVisibility(View.VISIBLE);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }
}
