// Render + audit the profile SVGs with the pre-installed Playwright Chromium.
//   node tools/verify.mjs <outDir>
// For every SVG: frames at 0/2/5/9/13 s (timeline seeked), a copy with all
// animation removed, prefers-reduced-motion, and real-time <img> renders.
// Also logs every network request, font load state, text overflow and alpha.
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.resolve(process.argv[2] || path.join(root, '.verify'));
fs.mkdirSync(out, { recursive: true });
const files = ['hero.svg', 'about-life.svg', 'stack.svg', 'id-dashboard.svg', 'connect.svg'];
const TIMES = [0, 2, 5, 9, 13];
const report = { generated: new Date().toISOString(), files: {} };

const browser = await chromium.launch();

function watch(page, bucket) {
  page.on('request', (r) => bucket.push(r.url().slice(0, 120)));
}

for (const f of files) {
  const abs = path.join(root, 'assets', f);
  const src = fs.readFileSync(abs, 'utf8');
  const [, w, h] = src.match(/<svg[^>]*width="(\d+)" height="(\d+)"/).map(Number);
  const rep = { width: w, height: h, bytes: fs.statSync(abs).size, requests: [], issues: [] };
  const stem = f.replace('.svg', '');

  // ---- 1. timeline frames (SVG as the document, timeline seeked deterministically)
  {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    watch(page, rep.requests);
    await page.goto(pathToFileURL(abs).href);
    await page.evaluate(() => document.fonts.ready);
    rep.fonts = await page.evaluate(() => [...document.fonts].map((x) => `${x.family} ${x.weight} ${x.status}`));
    for (const t of TIMES) {
      await page.evaluate((t) => {
        const svg = document.documentElement;
        svg.pauseAnimations();
        svg.setCurrentTime(t);
        for (const a of document.getAnimations()) { a.pause(); a.currentTime = t * 1000; }
      }, t);
      await page.waitForTimeout(60);
      await page.screenshot({ path: path.join(out, `${stem}-t${t}.png`), omitBackground: true });
    }
    // text overflow audit at the settled (13 s) state
    rep.textOverflow = await page.evaluate(({ w, h }) => {
      const bad = [];
      for (const t of document.querySelectorAll('text')) {
        if (t.closest('[clip-path]') || t.closest('defs') || t.querySelector('textPath')) continue;
        const cs = getComputedStyle(t);
        let hidden = false;
        for (let n = t; n && n.nodeType === 1; n = n.parentNode) {
          const s = getComputedStyle(n);
          if (s.display === 'none' || n.getAttribute('opacity') === '0') { hidden = true; break; }
        }
        if (hidden || cs.visibility === 'hidden') continue;
        const r = t.getBoundingClientRect();
        if (r.left < 6 || r.top < 6 || r.right > w - 6 || r.bottom > h - 6)
          bad.push(`${t.textContent.slice(0, 40)} [${r.left | 0},${r.top | 0},${r.right | 0},${r.bottom | 0}]`);
      }
      return bad;
    }, { w, h });
    await ctx.close();
  }

  // ---- 2. all animation removed (SMIL elements stripped + CSS animation off)
  {
    const stripped = src
      .replace(/<animate(Transform|Motion)?\b[^>]*\/>/g, '')
      .replace(/<set\b[^>]*\/>/g, '')
      .replace('</style>', '*{animation:none!important}</style>');
    const tmp = path.join(out, `${stem}-static.svg`);
    fs.writeFileSync(tmp, stripped);
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    watch(page, rep.requests);
    await page.goto(pathToFileURL(tmp).href);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(out, `${stem}-static.png`), omitBackground: true });
    // transparency: outside the rounded corner must be clear, the card opaque
    const px = await page.evaluate(async ({ w, h }) => {
      const blob = new Blob([new XMLSerializer().serializeToString(document.documentElement)], { type: 'image/svg+xml' });
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.src = url;
      await img.decode();
      const c = new OffscreenCanvas(w, h);
      const g = c.getContext('2d');
      g.drawImage(img, 0, 0);
      const a = (x, y) => g.getImageData(x, y, 1, 1).data[3];
      return { corners: [a(1, 1), a(w - 2, 1), a(1, h - 2), a(w - 2, h - 2)], centre: a(w >> 1, h >> 1), edgeMid: a(1, h >> 1) };
    }, { w, h });
    rep.alpha = px;
    if (px.corners.some((v) => v !== 0)) rep.issues.push('corner pixels not transparent');
    if (px.centre !== 255 || px.edgeMid !== 255) rep.issues.push('card body not opaque');
    fs.unlinkSync(tmp);
    await ctx.close();
  }

  // ---- 3. prefers-reduced-motion
  {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    watch(page, rep.requests);
    await page.goto(pathToFileURL(abs).href);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(out, `${stem}-reduced.png`), omitBackground: true });
    await ctx.close();
  }

  // ---- 4. as an <img> element (how GitHub embeds it), real time
  {
    const ctx = await browser.newContext({ viewport: { width: 860, height: Math.ceil((h * 830) / w) + 30 }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    watch(page, rep.requests);
    const html = path.join(out, `${stem}-img.html`);
    fs.writeFileSync(html, `<!doctype html><body style="margin:15px;background:#0d1117"><img id="i" src="${pathToFileURL(abs).href}?v=1" width="830"></body>`);
    await page.goto(pathToFileURL(html).href);
    const ok = await page.evaluate(() => { const i = document.getElementById('i'); return i.decode().then(() => i.naturalWidth); });
    rep.imgNaturalWidth = ok;
    for (const ms of [2000, 6000]) {
      await page.waitForTimeout(ms === 2000 ? 2000 : 4000);
      await page.screenshot({ path: path.join(out, `${stem}-img-${ms / 1000}s.png`) });
    }
    fs.unlinkSync(html);
    await ctx.close();
  }

  // blob: URLs come from this script's own alpha check, not from the SVG
  const external = rep.requests.filter((u) => !/^(file|data|blob):/.test(u));
  // static source checks
  if (/<script|foreignObject|@import|on[a-z]+=\"/i.test(src)) rep.issues.push('script/foreignObject/@import/event handler present');
  if (/(href|src)=\"(?!#|data:)/.test(src) || /url\((?!#|data:)/.test(src)) rep.issues.push('non-local href/url() reference');
  const prefix = stem === 'about-life' ? 'abt' : stem === 'id-dashboard' ? 'idc' : stem === 'connect' ? 'cnx' : stem === 'stack' ? 'stk' : 'hero';
  const ids = [...src.matchAll(/ id=\"([^\"]+)\"/g)].map((m) => m[1]);
  rep.idCount = ids.length;
  const badIds = ids.filter((i) => !i.startsWith(prefix + '-'));
  if (badIds.length) rep.issues.push(`un-namespaced ids: ${badIds.join(',')}`);
  if (new Set(ids).size !== ids.length) rep.issues.push('duplicate ids');
  const begins = [...src.matchAll(/begin=\"([^\"]+)\"/g)].map((m) => m[1]);
  if (begins.some((x) => x !== '0s')) rep.issues.push('SMIL begin other than 0s');
  const smil = (src.match(/<animate(Transform)?\b/g) || []).length;
  if (begins.length !== smil) rep.issues.push(`SMIL without begin: ${smil - begins.length}`);
  rep.smilCount = smil;
  rep.externalRequests = external;
  rep.requests = [...new Set(rep.requests.map((u) => u.split('?')[0].replace(/^file:\/\/.*\//, 'file://…/')))];
  if (external.length) rep.issues.push(`external requests: ${external.join(', ')}`);
  if (rep.fonts.some((s) => !s.endsWith('loaded'))) rep.issues.push('font not loaded');
  if (rep.textOverflow.length) rep.issues.push(`text near/outside edge: ${rep.textOverflow.join(' | ')}`);
  report.files[f] = rep;
  console.log(f, rep.issues.length ? rep.issues : 'OK');
}

// ---- 5. README-width and phone-width pages
for (const [name, vw, col] of [['desktop', 1012, 830], ['mobile', 390, 358]]) {
  const ctx = await browser.newContext({ viewport: { width: vw, height: 900 }, deviceScaleFactor: name === 'mobile' ? 2 : 1 });
  const page = await ctx.newPage();
  const html = path.join(out, `readme-${name}.html`);
  fs.writeFileSync(html, `<!doctype html><meta name=viewport content="width=device-width"><body style="margin:0;background:#0d1117"><div style="width:${col}px;margin:0 auto;padding:16px 0">${files.map((f) => `<img src="${pathToFileURL(path.join(root, 'assets', f)).href}?v=1" style="width:100%;display:block;margin:0 0 14px">`).join('')}</div></body>`);
  await page.goto(pathToFileURL(html).href);
  await page.waitForTimeout(14000);
  await page.screenshot({ path: path.join(out, `readme-${name}.png`), fullPage: true });
  fs.unlinkSync(html);
  await ctx.close();
}

await browser.close();
fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 1));
console.log('wrote', out);
