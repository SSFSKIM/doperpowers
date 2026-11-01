// Renders banner.html into the README banner (light and dark, transparent,
// 2x) and the GitHub social preview (1280x640, opaque, 1x).
// Needs Playwright (`npm i -g @playwright/cli` carries playwright-core, or any
// `playwright` install) and network access for the web font.
//   node docs/assets/render-banner.mjs
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
let chromium;
for (const mod of ['playwright', 'playwright-core', process.env.PLAYWRIGHT_CORE].filter(Boolean)) {
  try { ({ chromium } = require(mod)); break; } catch {}
}
if (!chromium) throw new Error('playwright not found: set PLAYWRIGHT_CORE to its module path');

const source = pathToFileURL(join(here, 'banner.html')).href;
const shots = [
  { query: 'kind=banner&theme=light', out: 'banner-light.png', w: 1280, h: 320, scale: 2, transparent: true },
  { query: 'kind=banner&theme=dark', out: 'banner-dark.png', w: 1280, h: 320, scale: 2, transparent: true },
  { query: 'kind=social', out: 'social-preview.png', w: 1280, h: 640, scale: 1, transparent: false },
];

const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
for (const s of shots) {
  const page = await browser.newPage({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: s.scale });
  await page.goto(`${source}?${s.query}`);
  await page.waitForSelector('body[data-ready="1"]');
  await page.locator('#canvas').screenshot({ path: join(here, s.out), omitBackground: s.transparent });
  await page.close();
  console.log('wrote', s.out);
}
await browser.close();
