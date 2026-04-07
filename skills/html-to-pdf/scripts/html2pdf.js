#!/usr/bin/env node
/**
 * HTML → single-page PDF generator
 *
 * Uses playwright-core bundled with agent-browser (no separate install needed).
 * Resolves the browser executable automatically from the ms-playwright cache.
 *
 * Usage:
 *   node html2pdf.js <input.html> [output.pdf] [--width=490]
 *
 * If output is omitted, writes to ~/Downloads/output.pdf
 * Width defaults to 490 (mobile pitch deck). Use 1440 for desktop layout.
 */

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

// --- Resolve playwright-core from agent-browser ---
function findPlaywrightCore() {
  try {
    const agentBrowserPath = execSync('which agent-browser', { encoding: 'utf-8' }).trim();
    const pwPath = path.join(path.dirname(agentBrowserPath), '..', 'lib', 'node_modules', 'agent-browser', 'node_modules', 'playwright-core');
    if (fs.existsSync(pwPath)) return pwPath;
  } catch {}

  // Fallback: try /tmp/node_modules/playwright (npm install playwright)
  const fallback = '/tmp/node_modules/playwright';
  if (fs.existsSync(fallback)) return fallback;

  console.error('ERROR: Cannot find playwright-core. Install agent-browser or run: cd /tmp && npm install playwright');
  process.exit(1);
}

// --- Resolve Chrome executable from ms-playwright cache ---
function findChromeBinary() {
  const cacheDir = path.join(process.env.HOME, 'Library', 'Caches', 'ms-playwright');
  if (!fs.existsSync(cacheDir)) {
    console.error('ERROR: ms-playwright cache not found at', cacheDir);
    process.exit(1);
  }

  // Find chromium-NNNN directories (not headless_shell), pick highest version
  const dirs = fs.readdirSync(cacheDir)
    .filter(d => /^chromium-\d+$/.test(d))
    .sort((a, b) => {
      const va = parseInt(a.split('-')[1]);
      const vb = parseInt(b.split('-')[1]);
      return vb - va; // descending
    });

  for (const dir of dirs) {
    const macPath = path.join(cacheDir, dir, 'chrome-mac-arm64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing');
    if (fs.existsSync(macPath)) return macPath;

    // Linux fallback
    const linuxPath = path.join(cacheDir, dir, 'chrome-linux', 'chrome');
    if (fs.existsSync(linuxPath)) return linuxPath;
  }

  console.error('ERROR: No Chrome binary found in', cacheDir);
  console.error('Available dirs:', dirs.join(', '));
  process.exit(1);
}

// --- Parse args ---
const args = process.argv.slice(2);
const flags = args.filter(a => a.startsWith('--'));
const positional = args.filter(a => !a.startsWith('--'));

const inputHtml = positional[0];
const outputPdf = positional[1] || path.join(process.env.HOME, 'Downloads', 'output.pdf');
const width = parseInt((flags.find(f => f.startsWith('--width=')) || '--width=490').split('=')[1]);
const heightBuffer = parseInt((flags.find(f => f.startsWith('--buffer=')) || '--buffer=50').split('=')[1]);

if (!inputHtml) {
  console.error('Usage: node html2pdf.js <input.html> [output.pdf] [--width=490] [--buffer=50]');
  process.exit(1);
}

// --- Generate PDF ---
(async () => {
  const pw = require(findPlaywrightCore());
  const chromePath = findChromeBinary();

  console.log(`Browser: ${path.basename(path.dirname(path.dirname(path.dirname(path.dirname(chromePath)))))}`);
  console.log(`Input:   ${inputHtml}`);
  console.log(`Width:   ${width}px`);

  const browser = await pw.chromium.launch({ executablePath: chromePath });
  const page = await browser.newPage({ viewport: { width, height: 844 } });

  // Resolve input path to file:// URL
  const fileUrl = inputHtml.startsWith('file://') ? inputHtml : `file://${path.resolve(inputHtml)}`;
  await page.goto(fileUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500); // allow fonts to load

  const scrollHeight = await page.evaluate(() => document.documentElement.scrollHeight);
  const pdfHeight = scrollHeight + heightBuffer;

  await page.pdf({
    path: outputPdf,
    width: `${width}px`,
    height: `${pdfHeight}px`,
    printBackground: true,
    margin: { top: '0', right: '0', bottom: '0', left: '0' }
  });

  await browser.close();
  console.log(`Output:  ${outputPdf}`);
  console.log(`Size:    ${width}x${pdfHeight}px (content: ${scrollHeight}px + ${heightBuffer}px buffer)`);

  // Verify page count
  try {
    const result = execSync(`mdls -name kMDItemNumberOfPages "${outputPdf}"`, { encoding: 'utf-8' });
    const pages = result.match(/(\d+)/);
    if (pages) console.log(`Pages:   ${pages[1]}`);
  } catch {}
})();
