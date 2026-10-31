const puppeteer = require('puppeteer-core');
(async () => {
  const b = await puppeteer.launch({ executablePath: '/tmp/chromium-sp', headless: 'shell',
    args: ['--no-sandbox','--disable-dev-shm-usage','--hide-scrollbars','--disable-gpu'],
    env: { ...process.env, LD_LIBRARY_PATH: '/tmp/al2023/lib:/tmp/al2023/usr/lib' } });
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  await p.goto('http://127.0.0.1:8000/chat', { waitUntil: 'networkidle2' }).catch(()=>{});
  await new Promise(r=>setTimeout(r,900));
  await p.screenshot({ path: '/tmp/cards-2x.png', clip: { x: 560, y: 340, width: 420, height: 200 } });
  await p.screenshot({ path: '/tmp/orb-2x.png', clip: { x: 500, y: 110, width: 320, height: 200 } });
  await b.close();
  console.log('ok');
})();
