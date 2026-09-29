# page.mjs: driving pages by element number

Every command prints a numbered table of what is clickable or editable in the viewport, plus a slice of visible text:

```
$ page.mjs open "https://example.com/search"
target=3FA9C21B https://example.com/search
title: Search  |  viewport 0-780 of 4200px
[2] searchbox "Search" = ""
[3] button "Search"
[4] select "Sort" = "Relevance" options: Relevance | Newest
[5] checkbox "Originals only" (checked)
[9] time "Delivery" = ""
--- visible text ---
```

Any unique prefix of the id works as `target`. Tabs open in the background. Actions dispatch real mouse and keyboard events, so framework-controlled inputs and anti-bot pages see a user, not `el.click()`.

## With a TypeSafe key (default)

```
page.mjs run "https://www.google.com/travel/flights?hl=en" "Search one-way flights from Zurich to London departing October 20, 2026, one adult, economy. Once results are shown, open the Stops filter and choose 'Nonstop only'. Stop when only nonstop flights are listed." --value origin=Zurich --value destination=London
page.mjs eval <target> "<expression that checks the outcome>"
page.mjs close <target>
```

- The goal is the user's, whole, one sentence per part; Jev sees the parts as a numbered list.
- Fields without a supplied value (date pickers, custom dropdowns) are operated by clicking.
- Output: status line, the tab(s) left open, a trace with each step's confidence, then the final table.
- Hand-back statuses: `UNSURE` (low confidence twice), `BLOCKED` (login, CAPTCHA, missing value), `STUCK`, `MAX_STEPS`, `NEEDS_CONFIRMATION` (the next click looks like paying, posting, sending or deleting). Do that step, then `run <target> "<same goal>"`.
- `DONE` is a belief: one `eval` confirms the outcome. Re-tracing the steps costs more than the run did.

## Without a key

```
page.mjs type 3FA9 2 "keyword" --enter
page.mjs select 3FA9 4 Newest
page.mjs type 3FA9 9 18:30                         # time/date fields take HH:MM / YYYY-MM-DD
page.mjs do 3FA9 'type 2 Ada' 'click 5' 'click 3'  # several actions on the current table; stops at the first FAILED
page.mjs scroll 3FA9 down
page.mjs wait 3FA9 "results found"                 # 10 s cap
```

Numbers stay valid until the page re-creates the element; a `FAILED` comes with the fresh table, pick again. Custom widgets: click to open, then click the option that appears. Do not batch across a step whose result you need to see (suggestions, navigation, dialogs). A click that opens a new tab is followed and the new id printed.

## Extraction

```
page.mjs eval 3FA9 "[...document.querySelectorAll('.result')].slice(0,50).map(r => ({title: r.querySelector('a')?.innerText.trim().slice(0,100), link: r.querySelector('a')?.href}))"
```

Limit count and length inside the expression; output beyond 8K chars is truncated. Page through large lists.

## Limits

Only the viewport is listed (`scroll` for more; a popup may open off-screen, so an empty table after a click usually means scroll). Open shadow DOM is traversed; cross-origin iframes are not. Uploads go through MCP `upload_file`. `clickable` rows are `cursor: pointer` targets without a declared role. Screenshot (`page.mjs shot`) only for canvas, image-only controls or layout questions; `take_snapshot` only on tiny pages that need MCP `fill`/`click` UIDs.
