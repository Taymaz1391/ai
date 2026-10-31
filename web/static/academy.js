/* رایان — آکادمی: ده درس فارسی با کد، آزمون و پیشرفت ذخیره‌شده */
(function () {
  "use strict";
  const R = window.RAYAN || {};
  const { $, nf, toast } = R;
  const KEY = "rayan.academy.v1";

  const LESSONS = [
    {
      id: "token",
      title: "توکن: مدل حرف نمی‌بیند، عدد می‌بیند",
      minutes: 6,
      summary: "متن فارسی چطور به قطعه‌های پرتکرار شکسته می‌شود و چرا نیم‌فاصله مهم است.",
      body: `
        <p>هر مدل زبانی پیش از هر چیز یک <b>توکنایزر</b> دارد. توکنایزر یک متن را به قطعه‌هایی می‌شکند که در پیکرهٔ آموزشی زیاد دیده شده‌اند. GPT-4 حدود ۲۰۰ هزار توکن دارد؛ رایان ۱۰ هزار توکن، آموزش‌دیده روی متن فارسی.</p>
        <p>سه تصمیم مهم در توکنایزر فارسی:</p>
        <ul>
          <li><b>نیم‌فاصله (ZWNJ) جزء واژه بماند</b> — وگرنه «می‌روم» به سه توکن بی‌ربط می‌شکند.</li>
          <li><b>نشانه‌گذاری به واژهٔ قبل بچسبد</b> — تا مدل یاد بگیرد جمله کجا تمام می‌شود.</li>
          <li><b>نرمال‌سازی پیش از کدگذاری</b> — ي→ی، ك→ک، حذف اعراب، یکسان‌سازی ارقام.</li>
        </ul>
        <p>اندازه‌گیری واقعی این مخزن: <b>۴٫۲۳ نویسه در هر توکن</b>. هر چه این عدد بیشتر باشد، متن بلندتری در همان زمینهٔ ۲۵۶ توکنی جا می‌شود.</p>
        <pre><code class="code-sample">from rayan.tokenizer import Tokenizer
tok = Tokenizer.load("tokenizer/rayan_bpe.json")
ids = tok.encode("می‌روم به خانه")
print(len("می‌روم به خانه"), "نویسه →", len(ids), "توکن")
print([tok.decode([i]) for i in ids])</code></pre>`,
      quiz: {
        q: "چرا نیم‌فاصله در توکنایزر فارسی نباید توکن جداگانه شود؟",
        options: ["چون فایل بزرگ‌تر می‌شود", "چون معنای واژه به آن وابسته است و توکن‌ها بی‌ربط می‌شوند", "چون پایتون آن را پشتیبانی نمی‌کند"],
        answer: 1,
        why: "«می‌روم» یک واژه است؛ شکستن آن به «می»، نیم‌فاصله و «روم»، معنا را از مدل می‌گیرد.",
      },
    },
    {
      id: "attention",
      title: "ترنسفورمر: تنها یک عملیات مهم است",
      minutes: 8,
      summary: "توجه، ماسک علّی، اتصال باقی‌مانده و دلیل اینکه چرا این معماری برنده شد.",
      body: `
        <p>قلب مدل، توجه است: هر توکن از توکن‌های قبلی می‌پرسد «چقدر به تو مربوطم؟»</p>
        <pre><code class="code-sample">Attention(Q, K, V) = softmax(Q·Kᵀ / √d + mask) · V</code></pre>
        <ul>
          <li><b>Q·Kᵀ</b>: شباهت پرسش هر توکن با کلید توکن‌های قبلی.</li>
          <li><b>mask</b>: ماتریس مثلثی؛ مدل آینده را نمی‌بیند.</li>
          <li><b>√d</b>: فقط برای پایدار ماندن اعداد در softmax.</li>
          <li><b>اتصال باقی‌مانده + LayerNorm</b>: تا آموزش عمیق ممکن شود.</li>
        </ul>
        <p>رایان ۵ لایه، ۴ سر توجه و بُعد ۲۵۶ دارد. پس‌انتشار دستی با NumPy نوشته شده و با گرادیان عددی تا خطای <b>۲٫۹۸e-۰۸</b> آزموده می‌شود:</p>
        <pre><code class="code-sample">python tests/gradcheck.py
# prompt KV gap = 2.98e-08
# next-token KV gap = 2.98e-08
# kvcheck OK</code></pre>`,
      quiz: {
        q: "نقش ماسک مثلثی در توجه چیست؟",
        options: ["سرعت بیشتر", "جلوگیری از دیدن توکن‌های آینده", "کاهش پارامترها"],
        answer: 1,
        why: "بدون ماسک، مدل هنگام پیش‌بینی توکن بعدی جواب را می‌بیند و هیچ چیز یاد نمی‌گیرد.",
      },
    },
    {
      id: "pretrain",
      title: "پیش‌آموزش: فقط «توکن بعدی چیست؟»",
      minutes: 7,
      summary: "کاهش آنتروپی متقابل، AdamW، warmup و اینکه چطور این کار ساده به درک زبان تبدیل می‌شود.",
      body: `
        <pre><code class="code-sample">loss = -mean(log(softmax(logits)[target_token]))</code></pre>
        <p>همین. کل پیش‌آموزش GPT هم در سطح مفهومی همین است؛ تفاوت در حجم داده، تعداد لایه‌ها و تعداد GPU است. برای پیش‌بینی دقیق‌تر واژهٔ بعد، مدل مجبور می‌شود نحو، ارجاع ضمیر، واقعیت‌های پرتکرار و سبک را در وزن‌هایش بگنجاند.</p>
        <p>سه عددی که باید بتوانی بخوانی:</p>
        <ul>
          <li><b>val loss = ۵٫۳۰ نات بر توکن</b> ≈ مدل مثل انتخاب از میان ۲۰۰ گزینه شک دارد.</li>
          <li><b>perplexity = ۲۰۱</b> همان عدد، به زبان «چند راه».</li>
          <li><b>top-1 = ۱۷٫۴٪</b> یعنی در ۱۷٪ مواقع واژهٔ درست را اول می‌آورد (تصادفی: ۰٫۰۱٪).</li>
        </ul>
        <p>رایان این‌ها را در ۱۳۵ دقیقه روی دو هستهٔ CPU و ۱۴٫۷ میلیون توکن گرفت؛ GPT-3 با ~۳۰۰ میلیارد توکن و هزاران GPU. کد یکی است، صفرها فرق می‌کند.</p>`,
      quiz: {
        q: "چرا خطای اعتبارسنجی (val loss) معیار اصلی پیش‌آموزش است؟",
        options: ["چون سریع‌تر محاسبه می‌شود", "چون روی دادهٔ دیده‌نشده اندازه‌گیری می‌شود", "چون به GPU نیاز ندارد"],
        answer: 1,
        why: "خطای آموزش می‌تواند با حفظ‌کردن داده پایین بیاید؛ اعتبارسنجی نشان می‌دهد مدل واقعاً تعمیم داده یا نه.",
      },
    },
    {
      id: "scaling",
      title: "مقیاس: چرا مدل‌ها را بزرگ می‌کنند؟",
      minutes: 6,
      summary: "قوانین مقیاس‌بندی، قاعدهٔ ۲۰ توکن به ازای هر پارامتر و درس عملی برای پروژه‌های کوچک.",
      body: `
        <p>خطای مدل با توانی از «پارامتر × داده × محاسبه» کاهش می‌یابد. قاعدهٔ سرانگشتی Chinchilla: برای آموزش بهینه، حدود <b>۲۰ توکن به ازای هر پارامتر</b>.</p>
        <table class="data-table">
          <thead><tr><th>مدل</th><th>پارامتر</th><th>توکن</th><th>نسبت</th></tr></thead>
          <tbody>
            <tr><td>رایان ۱</td><td>۶٫۵۷M</td><td>۱۴٫۷M</td><td>۲٫۲</td></tr>
            <tr><td>GPT-3</td><td>۱۷۵B</td><td>۳۰۰B</td><td>۱٫۷ (کم‌آموزش)</td></tr>
            <tr><td>Chinchilla</td><td>۷۰B</td><td>۱٫۴T</td><td>۲۰</td></tr>
          </tbody>
        </table>
        <p><b>درس عملی:</b> با ۶٫۵ میلیون پارامتر، افزودن دادهٔ بیشتر از چند دوره سود کمی دارد؛ اما <b>کیفیت داده و پس‌آموزش</b> سود زیادی دارد. اینجاست که به ChatGPT می‌رسیم.</p>`,
      quiz: {
        q: "طبق قاعدهٔ Chinchilla، برای ۱ میلیارد پارامتر چند توکن بهینه است؟",
        options: ["۲۰ میلیون", "۲۰۰ میلیون", "۲۰ میلیارد"],
        answer: 2,
        why: "۲۰ توکن به ازای هر پارامتر → ۲۰ میلیارد توکن برای ۱ میلیارد پارامتر.",
      },
    },
    {
      id: "sft",
      title: "SFT: از «تکمیل متن» به «پاسخ‌دادن»",
      minutes: 8,
      summary: "آموزش دستورالعمل، ماسک هزینهٔ پاسخ و چرا چند هزار نمونهٔ خوب از صدها هزار نمونهٔ متوسط بهتر است.",
      body: `
        <p>مدل پیش‌آموزش‌دیده ادامهٔ متن می‌دهد. اگر بپرسی «پایتخت فرانسه؟» ممکن است بنویسد «پایتخت فرانسه؟ این سؤال همیشه…». درمان: آموزش روی جفت‌های (دستور، پاسخ خوب).</p>
        <p>چهار جزئیاتی که همه اشتباه می‌کنند:</p>
        <ol>
          <li><b>قالب گفتگو</b>: <code>&lt;|user|&gt; … &lt;|bot|&gt; …</code></li>
          <li><b>ماسک هزینه</b>: loss فقط روی توکن‌های پاسخ، نه سؤال کاربر.</li>
          <li><b>توکن پایان</b>: مدل باید یاد بگیرد کجا ساکت شود.</li>
          <li><b>کیفیت بر کمیت</b>: چند هزار نمونهٔ باکیفیت کافی است.</li>
        </ol>
        <pre><code class="code-sample"># ماسک ساده: توکن‌های سؤال را نادیده بگیر
weights = [0] * prompt_len + [1] * answer_len
loss = -(logprobs * weights).sum() / max(sum(weights), 1)</code></pre>
        <p>رایان با ۱۴۰ نمونهٔ دست‌نویس فقط جوانهٔ این مرحله را دارد؛ همین باعث می‌شود گاهی سبک خبری یا شعری بگیرد.</p>`,
      quiz: {
        q: "اگر loss را روی توکن‌های سؤال هم حساب کنیم چه می‌شود؟",
        options: ["مدل سریع‌تر آموزش می‌بیند", "مدل یاد می‌گیرد سؤال بسازد به‌جای پاسخ‌دادن", "هیچ تفاوتی ندارد"],
        answer: 1,
        why: "مدل برای پیش‌بینی متن کاربر بهینه می‌شود، در حالی که هدف ما تولید پاسخ است.",
      },
    },
    {
      id: "rlhf",
      title: "RLHF و DPO: چرا «بهتر بودن» را با SFT نمی‌شود یاد داد",
      minutes: 9,
      summary: "مدل پاداش، جریمهٔ KL، هک‌کردن پاداش و نسخهٔ ارزان‌تر: DPO.",
      body: `
        <p>SFT می‌گوید «این پاسخ درست است»؛ نمی‌گوید «این پاسخ از آن یکی بهتر است». برای همین دو مرحله اضافه می‌شود:</p>
        <p><b>۱) مدل پاداش:</b> انسان‌ها دو پاسخ را مقایسه می‌کنند؛ یک مدل کوچک با تابع Bradley–Terry یاد می‌گیرد به پاسخ ترجیحی امتیاز بالاتر بدهد.</p>
        <p><b>۲) PPO:</b> مدل پاسخ می‌سازد، پاداش می‌گیرد و با یک جریمهٔ KL از مدل مرجع دور نمی‌شود:</p>
        <pre><code class="code-sample">هدف = E[ reward(x, y) ] − β · KL( π_new ‖ π_ref )</code></pre>
        <p>بدون KL، مدل «پاداش را هک می‌کند»: پاسخ‌های چاپلوس و توخالی می‌دهد که امتیاز بالا می‌گیرند.</p>
        <p><b>DPO</b> نسخهٔ ارزان‌تر است: نه مدل پاداش، نه PPO؛ فقط جفت‌های ترجیحی:</p>
        <pre><code class="code-sample">loss = -log σ( β·[log π(win)/π_ref(win) − log π(lose)/π_ref(lose)] )</code></pre>
        <p>و <b>RLAIF</b> بازخورد را از مدل دیگری می‌گیرد؛ <b>RLVR</b> برای ریاضی و کد پاداش را از «درست بودن جواب» می‌گیرد — همان چیزی که مدل‌های استدلالی امروز را ساخت.</p>`,
      quiz: {
        q: "جریمهٔ KL در RLHF چه کاری می‌کند؟",
        options: ["آموزش را سریع‌تر می‌کند", "مانع دورشدن زیاد از مدل مرجع و هک‌کردن پاداش می‌شود", "پاسخ‌ها را کوتاه‌تر می‌کند"],
        answer: 1,
        why: "KL مثل طناب نگه‌دارنده است؛ مدل می‌تواند بهتر شود اما نه به قیمت خراب‌کردن زبان.",
      },
    },
    {
      id: "inference",
      title: "استنتاج: چرا پاسخ‌ها کلمه‌به‌کلمه می‌آیند؟",
      minutes: 6,
      summary: "حافظهٔ KV، نمونه‌گیری با دما و top-p و حس سرعت در رابط کاربری.",
      body: `
        <p>بدون حافظهٔ KV، تولید هر توکن نیاز دارد کل پیش‌آموزش دوباره محاسبه شود: هزینهٔ O(n²). با KV، فقط توکن تازه محاسبه می‌شود: O(n).</p>
        <pre><code class="code-sample">logits, kv = model.logits_for_prompt(ids)
for step in range(max_new_tokens):
    token = sample(logits, temperature=0.82, top_p=0.9)
    logits, kv = model.next_logits(token, pos, kv)   # فقط یک توکن</code></pre>
        <p>سه اهرم کیفیت خروجی:</p>
        <ul>
          <li><b>دما</b>: پایین = محافظه‌کار، بالا = خلاق و پرخطا.</li>
          <li><b>top-p</b>: فقط توکن‌هایی که احتمال تجمعی‌شان به p می‌رسد.</li>
          <li><b>جریمهٔ تکرار</b>: جلوگیری از حلقه‌های تکراری.</li>
        </ul>
        <p>و آن حس «سریع بودن» ChatGPT بیشتر از معماری، از <b>ارسال تدریجی</b> می‌آید: همان <code>start → token → done</code> که در <code>/api/chat/stream</code> پیاده شده است.</p>`,
      quiz: {
        q: "حافظهٔ KV چه هزینه‌ای را کاهش می‌دهد؟",
        options: ["حافظهٔ دیسک", "محاسبهٔ دوبارهٔ توکن‌های قبلی در هر گام", "حجم مدل"],
        answer: 1,
        why: "با نگه‌داشتن کلید/مقدار لایه‌ها، هر گام فقط توکن تازه را پردازش می‌کند.",
      },
    },
    {
      id: "product",
      title: "محصول: چه چیزی ChatGPT را «ChatGPT» می‌کند؟",
      minutes: 7,
      summary: "حساب کاربری، تاریخچه، سهمیه، اشتراک‌گذاری، ابزارها، حافظه و ایمنی.",
      body: `
        <p>مدل خوب کافی نیست. آنچه تجربهٔ ChatGPT را می‌سازد، لایه‌های اطراف مدل است:</p>
        <table class="data-table">
          <thead><tr><th>لایه</th><th>کار</th><th>در رایان</th></tr></thead>
          <tbody>
            <tr><td>حساب و تاریخچه</td><td>گفتگوها بمانند</td><td>SQLite + کوکی نشست</td></tr>
            <tr><td>سهمیه و ضدسوءاستفاده</td><td>سرور نمیرد</td><td>۲۵/۲۰۰/۳۰۰۰ + ۴۵ در دقیقه</td></tr>
            <tr><td>اشتراک‌گذاری</td><td>رشد ارگانیک</td><td><code>/s/{token}</code></td></tr>
            <tr><td>شفافیت</td><td>اعتماد</td><td>توکن، اطمینان، سرعت</td></tr>
            <tr><td>ابزار (function calling)</td><td>محاسبه، تاریخ</td><td>حساب‌گر و تقویم شمسی</td></tr>
            <tr><td>RAG</td><td>پاسخ از سند خودت</td><td>گام بعدی</td></tr>
          </tbody>
        </table>
        <p>هر لایهٔ محصول، یک شکست ممکن را حذف می‌کند: بدون سهمیه، سرور می‌خوابد؛ بدون شفافیت، کاربر اعتماد نمی‌کند؛ بدون ابزار، مدل کوچک در حساب اشتباه می‌کند.</p>`,
      quiz: {
        q: "چرا محدودیت نرخ برای یک محصول گفتگو ضروری است؟",
        options: ["برای زیبایی", "چون تولید توکن گران است و سوءاستفاده سرویس را می‌خواباند", "چون مرورگر محدودیت دارد"],
        answer: 1,
        why: "یک اسکریپت می‌تواند صدها درخواست در دقیقه بفرستد و صف مدل را برای همه پر کند.",
      },
    },
    {
      id: "eval",
      title: "ارزیابی: بدون آن، همه‌چیز حدس است",
      minutes: 6,
      summary: "perplexity، آزمون ثابت انسانی، مقایسهٔ زوجی و Elo.",
      body: `
        <p>چهار سطح ارزیابی:</p>
        <ol>
          <li><b>خودکار</b>: perplexity (فقط کیفیت زبانی)، MMLU (دانش)، GSM8K (ریاضی).</li>
          <li><b>انسانی</b>: امتیاز ۱–۵ روی ۱۰۰ پرسش ثابت؛ نرخ تکرار، نرخ فارسی‌بودن، جملهٔ ناتمام.</li>
          <li><b>ترجیحی</b>: مقایسهٔ زوجی → Elo (همان کاری که Chatbot Arena می‌کند).</li>
          <li><b>پایه</b>: همیشه با نسخهٔ قبلی مقایسه کن، نه با آرزو.</li>
        </ol>
        <p>در رایان، <code>reports/evaluation.json</code> و <code>tests/</code> همین کار را انجام می‌دهند؛ قدم بعدی یک «آزمون ۱۰۰ پرسشی» ثابت با خروجی قابل‌مقایسه است.</p>`,
      quiz: {
        q: "چرا perplexity به‌تنهایی برای ارزیابی یک دستیار کافی نیست؟",
        options: ["خیلی کند است", "کیفیت زبانی را می‌سنجد، نه درست بودن یا مفید بودن پاسخ", "فقط برای انگلیسی کار می‌کند"],
        answer: 1,
        why: "جملات روان و کاملاً غلط می‌توانند perplexity پایین داشته باشند.",
      },
    },
    {
      id: "roadmap",
      title: "نقشهٔ راه: از ۶٫۵ میلیون تا دستیار واقعی",
      minutes: 5,
      summary: "پنج گام عملی و قابل سنجش برای ارتقای رایان.",
      body: `
        <ol>
          <li><b>SFT واقعی</b>: ماسک هزینهٔ پاسخ + ۵ تا ۱۰ هزار جفت دستور/پاسخ فارسی + آزمون ۱۰۰ پرسشی.</li>
          <li><b>DPO سبک</b>: ۲٬۰۰۰ جفت ترجیحی که با امتیازدهی <code>rayan/thinking.py</code> خودکار ساخته می‌شود.</li>
          <li><b>RAG فارسی</b>: ایندکس BM25 روی پیکرهٔ خودمان + ارجاع به منبع؛ دانش را از وزن به بازیابی منتقل می‌کند.</li>
          <li><b>ابزارها</b>: حساب‌گر، تقویم شمسی، تبدیل یکا و جست‌وجوی محلی با قالب JSON.</li>
          <li><b>بزرگ‌ترکردن مدل</b>: از ۶٫۵M به ~۵۰M پارامتر با همان کد NumPy روی GPU رایگان؛ فقط صبر و داده لازم است.</li>
        </ol>
        <p>هیچ‌کدام از این‌ها به API بیرونی نیاز ندارد. همه از داده و کد خودت می‌آید.</p>`,
      quiz: {
        q: "کدام گام بیشترین جهش کیفی را برای یک مدل کوچک دارد؟",
        options: ["بزرگ‌کردن واژگان", "آموزش روی جفت‌های دستور/پاسخ باکیفیت (SFT)", "افزودن لایه‌های بیشتر بدون داده"],
        answer: 1,
        why: "کوچک‌ترین مدل‌ها هم با SFT درست، از «تکمیل متن» به «دستیار» تبدیل می‌شوند.",
      },
    },
  ];

  function loadProgress() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "{}");
    } catch {
      return {};
    }
  }

  function saveProgress(data) {
    try { localStorage.setItem(KEY, JSON.stringify(data)); } catch { /* نادیده */ }
  }

  function esc(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function render() {
    const progress = loadProgress();
    const list = $("#lesson-list");
    list.innerHTML = LESSONS.map((lesson, index) => {
      const done = progress[lesson.id] === true;
      return `<article class="lesson ${done ? "is-done" : ""}" id="lesson-${lesson.id}">
        <button class="lesson-head" aria-expanded="false" data-lesson="${lesson.id}">
          <span class="lesson-num">${nf(index + 1)}</span>
          <span class="lesson-title"><b>${esc(lesson.title)}</b><small>${esc(lesson.summary)}</small></span>
          <span class="lesson-meta"><span class="pill ${done ? "is-ok" : ""}">${done ? "خوانده‌شده" : nf(lesson.minutes) + " دقیقه"}</span>
            <span class="lesson-chevron" aria-hidden="true">⌄</span></span>
        </button>
        <div class="lesson-body">
          <div class="lesson-content">${lesson.body}</div>
          <div class="quiz" data-quiz="${lesson.id}">
            <h4>آزمون کوتاه</h4>
            <p>${esc(lesson.quiz.q)}</p>
            <div class="quiz-options">
              ${lesson.quiz.options.map((opt, i) => `<button type="button" data-opt="${i}">${esc(opt)}</button>`).join("")}
            </div>
            <p class="quiz-why" hidden>${esc(lesson.quiz.why)}</p>
          </div>
        </div>
      </article>`;
    }).join("");
    updateProgressBar();
  }

  function updateProgressBar() {
    const progress = loadProgress();
    const done = LESSONS.filter((l) => progress[l.id]).length;
    const percent = Math.round((done / LESSONS.length) * 100);
    const bar = $("#course-progress");
    const label = $("#progress-label");
    if (bar) bar.style.width = `${percent}%`;
    if (label) label.textContent = `${nf(done)} از ${nf(LESSONS.length)} درس${done === LESSONS.length ? " — تمام شد 🎉" : ""}`;
  }

  document.addEventListener("click", (event) => {
    const head = event.target.closest("[data-lesson]");
    if (head) {
      const lesson = head.closest(".lesson");
      const open = lesson.classList.toggle("is-open");
      head.setAttribute("aria-expanded", String(open));
      return;
    }
    const opt = event.target.closest("[data-opt]");
    if (opt) {
      const quiz = opt.closest("[data-quiz]");
      const id = quiz.dataset.quiz;
      const data = LESSONS.find((l) => l.id === id);
      const choice = Number(opt.dataset.opt);
      quiz.querySelectorAll("[data-opt]").forEach((b) => b.classList.remove("is-right", "is-wrong"));
      const correct = choice === data.quiz.answer;
      opt.classList.add(correct ? "is-right" : "is-wrong");
      if (!correct) quiz.querySelector(`[data-opt="${data.quiz.answer}"]`).classList.add("is-right");
      quiz.querySelector(".quiz-why").hidden = false;
      if (correct) {
        const progress = loadProgress();
        progress[id] = true;
        saveProgress(progress);
        quiz.closest(".lesson").classList.add("is-done");
        updateProgressBar();
        if (R.toast) R.toast("آفرین! درس ثبت شد.", "ok");
      }
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    render();
    if (location.hash.startsWith("#lesson-")) {
      const node = document.querySelector(location.hash);
      if (node) {
        node.classList.add("is-open");
        node.querySelector(".lesson-head").setAttribute("aria-expanded", "true");
      }
    }
  });
})();
