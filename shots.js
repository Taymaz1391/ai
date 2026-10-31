const puppeteer = require('puppeteer-core');
(async () => {
  const b = await puppeteer.launch({ executablePath: '/tmp/chromium-sp', headless: 'shell',
    args: ['--no-sandbox','--disable-dev-shm-usage','--hide-scrollbars','--disable-gpu'],
    env: { ...process.env, LD_LIBRARY_PATH: '/tmp/al2023/lib:/tmp/al2023/usr/lib' } });
  const p = await b.newPage();
  for (const spec of process.argv.slice(2)) {
    const [path, w, h, full, name] = spec.split('|');
    await p.setViewport({ width: Number(w||1440), height: Number(h||900), deviceScaleFactor: 1 });
    await p.goto('http://127.0.0.1:8000' + path, { waitUntil: 'networkidle2', timeout: 45000 }).catch(()=>{});
    await new Promise(r => setTimeout(r, 1200));
    await p.screenshot({ path: `/tmp/${name}.png`, fullPage: full === 'full' });
    console.log('saved', name);
  }
  await b.close();
})().catch(e => { console.error('ERR', e.message); process.exit(1); });
