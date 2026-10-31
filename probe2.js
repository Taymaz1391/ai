const puppeteer = require('puppeteer-core');
(async () => {
  const b = await puppeteer.launch({ executablePath: '/tmp/chromium-sp', headless: 'shell',
    args: ['--no-sandbox','--disable-dev-shm-usage','--hide-scrollbars','--disable-gpu'],
    env: { ...process.env, LD_LIBRARY_PATH: '/tmp/al2023/lib:/tmp/al2023/usr/lib' } });
  const p = await b.newPage();
  await p.setViewport({ width: 1440, height: 900 });
  await p.goto('http://127.0.0.1:8000/chat', { waitUntil: 'networkidle2' }).catch(()=>{});
  await new Promise(r=>setTimeout(r,900));
  console.log(JSON.stringify(await p.evaluate(() => {
    const out = [];
    for (const [x,y] of [[700,395],[720,400],[740,392]]) {
      const el = document.elementFromPoint(x,y);
      out.push([x,y, el && el.tagName, el && el.className, el && (el.textContent||'').slice(0,24)]);
    }
    // also list any element with a background image/gradient inside the card
    const card = document.querySelector('.suggestion');
    const walk = [];
    if (card) card.querySelectorAll('*').forEach(e => {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage !== 'none' || cs.boxShadow !== 'none' || cs.filter !== 'none') {
        walk.push([e.tagName, e.className, cs.backgroundImage.slice(0,60), cs.boxShadow.slice(0,40), cs.filter]);
      }
    });
    return { out, walk, cardHTML: card && card.outerHTML.slice(0, 400) };
  }), null, 1));
  await b.close();
})();
