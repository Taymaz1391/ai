const puppeteer = require('puppeteer-core');
(async () => {
  const b = await puppeteer.launch({ executablePath: '/tmp/chromium-sp', headless: 'shell',
    args: ['--no-sandbox','--disable-dev-shm-usage','--hide-scrollbars','--disable-gpu'],
    env: { ...process.env, LD_LIBRARY_PATH: '/tmp/al2023/lib:/tmp/al2023/usr/lib' } });
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 1000 });
  for (const spec of process.argv.slice(2)) {
    const [url, y, name] = spec.split('|');
    await p.goto('http://127.0.0.1:8000' + url, { waitUntil: 'networkidle2' }).catch(()=>{});
    await new Promise(r=>setTimeout(r,700));
    await p.evaluate((yy) => window.scrollTo(0, Number(yy)), y);
    await new Promise(r=>setTimeout(r,700));
    await p.screenshot({ path: `/tmp/${name}.png` });
    console.log('saved', name);
  }
  await b.close();
})();
