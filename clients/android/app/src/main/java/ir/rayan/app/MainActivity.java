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

/**
 * کلاینت نازک رایان.
 *
 * <p>هیچ تصمیم امنیتی یا سهمیه‌ای در این‌جا گرفته نمی‌شود: نشست، نقش مدیر و
 * سهمیهٔ مصرف همه سمت سرور تعیین می‌شوند. این پوسته فقط صفحهٔ همان سرور را
 * نمایش می‌دهد و اجازه نمی‌دهد کاربر با دست‌کاری کلاینت، «آنلاین» یا «ویژه»
 * جا بزند.</p>
 */
public class MainActivity extends Activity {

    private WebView web;
    private View errorView;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_main);
        web = findViewById(R.id.web);
        errorView = findViewById(R.id.error);

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
        s.setUserAgentString(s.getUserAgentString() + " RayanAndroid/" + BuildConfig.VERSION_NAME);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, false);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (uri.getHost() != null && uri.getHost().equals(Uri.parse(BuildConfig.SERVER_URL).getHost())) {
                    return false; // همان سرور: داخل برنامه
                }
                startActivity(new Intent(Intent.ACTION_VIEW, uri)); // بقیه: مرورگر
                return true;
            }

            @Override
            public void onReceivedError(WebView view, int code, String description, String failingUrl) {
                if (failingUrl != null && failingUrl.startsWith(BuildConfig.SERVER_URL)) {
                    showError();
                }
            }
        });

        findViewById(R.id.retry).setOnClickListener(v -> {
            errorView.setVisibility(View.GONE);
            web.setVisibility(View.VISIBLE);
            web.loadUrl(BuildConfig.SERVER_URL);
        });

        web.loadUrl(BuildConfig.SERVER_URL);
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
