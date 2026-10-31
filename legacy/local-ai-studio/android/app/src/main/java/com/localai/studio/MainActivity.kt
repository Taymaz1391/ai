package com.localai.studio
import android.app.Activity
import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
class MainActivity : Activity() {
 companion object { const val LOCAL_AI_URL="http://10.0.2.2:8000" }
 override fun onCreate(state:Bundle?) { super.onCreate(state); val web=WebView(this); web.webViewClient=WebViewClient(); web.settings.javaScriptEnabled=true; web.settings.domStorageEnabled=true; web.loadUrl(LOCAL_AI_URL); setContentView(web) }
}
