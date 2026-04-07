---
name: html-to-pdf
description: |
  Convert styled HTML files to high-quality single-page PDFs using headless Chrome via playwright-core.
  Use this skill whenever the user asks to generate a PDF from HTML, export a webpage to PDF,
  create a no-page-break long-scroll PDF, convert a pitch deck / BP / report HTML to PDF,
  or mentions "导出 PDF", "生成 PDF", "HTML 转 PDF", "nopagebreak PDF".
  Also use when iterating on a document with edit-then-export cycles (edit HTML → regenerate PDF → review → repeat).
  Also use when an interactive/animated HTML presentation needs to be flattened to a static PDF.
---

# HTML to PDF

Generate single-page (no page break) PDFs from styled HTML using headless Chrome. Designed for pitch decks, reports, and long-scroll documents where the entire content should be one continuous page.

## When to use

- Converting a styled HTML document to PDF (especially dark-themed, custom-CSS pages)
- Flattening an interactive/animated HTML presentation to a static, shareable PDF
- Iterative document editing: user gives feedback → edit HTML → regenerate PDF → send for review
- Exporting mobile-optimized HTML as a shareable PDF
- Any scenario where `@media print` or browser "Save as PDF" produces broken results

## Golden rule: work on a copy

Never modify the original HTML. Always copy to a working file first (e.g., `cp original.html original-print.html`). If the file came from WeChat or other apps, it may be read-only — `chmod u+w` the copy before editing.

## Step zero: neutralize dynamic elements

Interactive HTML presentations (slide decks, scroll-snap pages) contain elements that break PDF rendering. The PDF captures the page at a single moment — animations frozen at their initial state, scroll-snapped slides stacked on one viewport. Before generating a PDF, the HTML must be flattened to a static, continuous-scroll document.

Common dynamic elements that cause blank or broken PDFs:

| Element | Problem in PDF | Fix |
|---------|---------------|-----|
| **Scroll snapping** (`scroll-snap-type: y mandatory`) | Each slide fills exactly one viewport, PDF only captures the first | `scroll-snap-type: none` |
| **IntersectionObserver animations** (`.anim { opacity: 0 }`) | Elements are invisible — they only animate in on scroll | `.anim { opacity: 1 !important; transform: none !important; }` |
| **Fixed slide heights** (`height: 100vh`) | Each section is viewport-locked, content can overflow or be clipped | `height: auto !important; min-height: auto !important;` |
| **Navigation UI** (nav dots, progress bars, key hints) | Floating UI renders over content | `display: none !important` |
| **Lightbox overlays** | Empty overlay markup takes up space or covers content | `display: none !important` |
| **Decorative pseudo-elements** (`::before`, `::after` ink splashes) | Can create visual noise or extra whitespace | `display: none !important` |
| **`position: absolute` on content** (footers, slide numbers using `bottom: Xvh`) | Once `100vh` is removed, these float to wrong positions and overlap content | Change to `position: relative; margin-top: auto` |

**How to apply the fix** — add a CSS override block at the end of the `<style>` section (before the closing `</style>` tag). This is a surgical approach: the original interactive CSS stays intact for browser viewing, while the overrides flatten everything for PDF export. Example pattern:

```css
/* ====== PDF/STATIC OVERRIDES ====== */
html { scroll-snap-type: none; }
.slide { height: auto !important; min-height: auto !important; }
.anim { opacity: 1 !important; transform: none !important; }
.nav-dots, .progress, .lightbox, .ink-splash, #keyHint { display: none !important; }
body::before, .slide::after { display: none !important; }
```

The specific selectors depend on the HTML — inspect the source to find which classes are used for animations, navigation, and decorative elements. The pattern is always the same: force visible, auto-height, hide interactive UI.

**After removing `100vh`, check for displaced elements.** Any content element using `position: absolute; bottom: Xvh` (common for slide footers, page numbers) will be mispositioned once slides become auto-height. Convert these to document flow: `position: relative; margin-top: 1.5rem; text-align: right`.

## CSS properties: safe vs unsafe in PDF

Chrome's PDF renderer handles most CSS well, but some properties produce artifacts:

| Safe | Unsafe (causes PDF artifacts) |
|------|------|
| `color`, `background-color`, `background` (solid) | `background-clip: text` + `-webkit-text-fill-color: transparent` → **black horizontal lines** |
| `border`, `padding`, `margin`, `font-*` | `backdrop-filter: blur()` → ignored or renders incorrectly |
| `flex`, `grid`, `border-radius` | `position: fixed` → breaks in continuous-scroll layout |
| `box-shadow` (simple) | Complex `filter:` chains → may not render |

**The `background-clip: text` pitfall deserves special attention.** Gradient text using `background-clip: text` + `-webkit-text-fill-color: transparent` renders beautifully in the browser but produces **black horizontal line artifacts** in Chrome's PDF engine. Replace the gradient with a simple `color` value.

## Generating the PDF

Use the bundled `scripts/html2pdf.js` script. It handles browser resolution automatically:

```
node ${SKILL_PATH}/scripts/html2pdf.js <input.html> [output.pdf] [--width=490] [--buffer=50]
```

The script resolves `playwright-core` from `agent-browser`'s bundled copy (no separate install), finds the Chrome binary from the `ms-playwright` cache (picking the highest available version), and generates a single-page PDF by measuring `scrollHeight` and adding a buffer to prevent page overflow.

## Key decisions

**Width selection** — determines the visual layout and which CSS breakpoints fire:

| Width | Use case |
|-------|----------|
| 390-430 | iPhone-sized, very compact |
| 490-500 | Mobile pitch deck (sweet spot for BP/路演 documents) |
| 768 | Tablet |
| 1440 | Desktop full-width |

Test a few widths if the layout looks wrong — width changes can trigger different responsive breakpoints and produce dramatically different layouts.

**Buffer** — the `--buffer` parameter (default 50px) adds extra height beyond `scrollHeight` to prevent a blank second page. Chrome's PDF renderer can round heights slightly differently than the DOM reports. If the output has 2 pages with a blank second page, increase the buffer. If there's too much whitespace at the bottom, decrease it.

## Pitfalls

**Don't install playwright separately.** The `agent-browser` package already bundles `playwright-core` with a compatible Chrome. Installing a standalone `playwright` creates version mismatches — the library expects one browser revision while the cache has another. The script resolves this automatically.

**Browser version mismatch.** If the script reports a missing executable, it means the cached Chrome revision doesn't match what `playwright-core` expects. The script works around this by scanning the cache for the highest available version. If even that fails, `npx playwright install chromium` fetches the matching version.

**Single-page verification.** After generating, verify with `mdls -name kMDItemNumberOfPages output.pdf` (macOS). If it shows 2 pages, the content overflowed — increase the buffer. The script does this check automatically.

**Font loading.** The script waits 1.5s after page load for web fonts. If the HTML loads fonts from a CDN that's slow or blocked (e.g., Google Fonts in China), fonts may not render. Self-hosted fonts in the HTML avoid this issue.

**Print CSS interference.** Some HTML files have `@media print` rules that hide elements or change layout. The PDF is generated from the print rendering. If elements disappear in the PDF, check for print-specific CSS.

**`agent-browser pdf` doesn't work for this use case.** It exports to A4 with white background and pagination — losing dark themes entirely and breaking single-page layout. Always use the bundled playwright script instead.

## QA: visual inspection before delivery

After generating the PDF, do a visual QA pass before delivering. Open the HTML in a headless browser and take screenshots at the target width to verify:

1. All content is visible (no opacity: 0 remnants)
2. No overlapping elements (especially after removing fixed heights)
3. Text is readable at the chosen width
4. No black line artifacts from `background-clip: text`
5. Dark backgrounds are preserved (not rendered as white)

For section-by-section inspection, scroll to each major section (`scrollIntoView`) and take viewport screenshots. This catches issues that full-page screenshots may miss at scale.

## Iterative workflow

When the user is doing edit→export cycles (e.g., iterating on a pitch deck):

1. Edit the HTML source (apply text changes, layout fixes)
2. If the source of truth is a separate file (markdown, etc.), keep it in sync with the HTML
3. Regenerate with the same width as previous iterations for visual consistency
4. Verify page count — especially after adding content, since longer text can push the height past the buffer threshold
5. Deliver the PDF to the user
