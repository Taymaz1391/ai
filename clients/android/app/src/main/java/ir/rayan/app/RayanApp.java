package ir.rayan.app;

import android.app.Application;
import android.webkit.WebView;

/** تنظیمات مشترک فرایند؛ در دیباگ، بازرسی WebView روشن می‌شود. */
public class RayanApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        if (Config.DEBUG) {
            WebView.setWebContentsDebuggingEnabled(true);
        }
    }
}
