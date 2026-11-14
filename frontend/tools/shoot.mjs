// Screenshots of the built app for visual checks: node tools/shoot.mjs
import puppeteer from 'puppeteer-core';
import { preview } from 'vite';

const server = await preview({ preview: { port: 4173, strictPort: true }, logLevel: 'silent' });
const base = 'http://localhost:4173/';
const browser = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome',
  args: ['--no-sandbox', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--hide-scrollbars'],
});
const only = process.argv[2];
const shots = [
  ['fhd-queue', '#/', 1920, 1080, 'light', false],
  ['fhd-case', '#/case/C-1047?t=18500', 1920, 1080, 'light', false],
  ['fhd-report', '#/case/C-1047?t=36000&tab=report', 1920, 1080, 'dark', true],
  ['queue', '#/', 1440, 900, 'light', true],
  ['case-start', '#/case/C-1047', 1440, 900, 'light', false],
  ['case-docs', '#/case/C-1047?t=5600', 1440, 900, 'light', true],
  ['case-agents', '#/case/C-1047?t=18500', 1440, 900, 'light', true],
  ['case-judge', '#/case/C-1047?t=25300', 1440, 900, 'light', true],
  ['case-round2', '#/case/C-1047?t=28500', 1440, 900, 'dark', true],
  ['case-done', '#/case/C-1047?t=36000', 1440, 900, 'light', true],
  ['report', '#/case/C-1047?t=36000&tab=report', 1440, 900, 'light', true],
  ['report-dark', '#/case/C-1047?t=36000&tab=report', 1440, 900, 'dark', true],
  ['wind-agents', '#/case/C-1042?t=16000', 1440, 900, 'dark', true],
  ['wind-report', '#/case/C-1042?t=24500&tab=report', 1280, 800, 'light', true],
  ['queue-dark', '#/', 1440, 900, 'dark', true],
  ['case-1024', '#/case/C-1047?t=18500', 1024, 768, 'light', true],
  ['case-390', '#/case/C-1047?t=18500', 390, 844, 'light', true],
  ['report-390', '#/case/C-1047?t=36000&tab=report', 390, 844, 'dark', true],
  ['queue-390', '#/', 390, 844, 'light', true],
];
const errors = [];
for (const [name, hash, w, h, theme, full] of shots) {
  if (only && !name.includes(only)) continue;
  const page = await browser.newPage();
  page.on('pageerror', (e) => errors.push(`${name}: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && errors.push(`${name}: ${m.text()}`));
  await page.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
  await page.evaluateOnNewDocument((t) => localStorage.setItem('asigit-theme', t), theme);
  await page.goto(base + hash, { waitUntil: 'load', timeout: 90000 });
  // Full-page capture resizes the viewport, which would replay the rail's entrance mid-shot.
  await page.addStyleTag({ content: '.node,.lane,.seg,.loop{animation:none !important}' });
  await new Promise((r) => setTimeout(r, 3000));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (overflow > 0) errors.push(`${name}: horizontal overflow ${overflow}px`);
  await page.screenshot({ path: `shots/${name}.png`, fullPage: full });
  await page.close();
}
console.log(errors.length ? errors.join('\n') : 'no errors');
await browser.close();
server.httpServer.close();
process.exit(0);
