---
name: cdp-chrome
description: |
  Optional per-OS-user headed Chrome provider for browser automation. Use ONLY
  when the task needs this instance's unique capabilities: logged-in sessions,
  anti-bot/real-browser fingerprint, or a GUI the user watches (social media,
  logged-in sites, anti-bot pages). Stateless browsing (screenshots, DOM/text
  extraction, local build review, login-free interaction) belongs to lighter
  on-demand tools such as the agent-browser CLI, not this shared instance.
---

# CDP Chrome: Per-User Headed Browser Provider

Optional implementation of the abstract `headed-browser` capability. It connects to a normal GUI Chrome with a persistent profile (no `--enable-automation`, so `navigator.webdriver` stays false). One process per OS user, shared by that user's agents.

## Tier first

cdp-chrome is reserved for tasks that need **a logged-in session, a real-browser fingerprint, or a GUI the user watches**. Name which one the task needs; if you can't, use the lightweight tier: the `agent-browser` CLI if installed (`agent-browser skills get core` for usage; `--session <unique-name>` for isolation), or one-shot `chrome --headless=new --screenshot=… / --dump-dom <URL>` with a temporary `--user-data-dir`.

## Config

steroids config file: macOS/Linux `~/.config/steroids.json`, Windows `%APPDATA%\steroids.json` (shell: `${APPDATA:-$HOME/.config}/steroids.json`).

```json
{ "cdp-chrome": { "port": 9224, "profile_dir": "~/.config/cdp-chrome/profile" } }
```

| Optional key | Default | Meaning |
|---|---|---|
| `log_dir` | `~/.config/cdp-chrome/logs` (Windows `%APPDATA%\cdp-chrome\logs`) | `page.mjs` execution log; `false` disables |
| `typesafe_api_key` | unset | TypeSafe key for `page.mjs run`; the `TYPESAFE_API_KEY` env var takes precedence and is the better place |
| `jev_model` | `jev-latest` | Pin a versioned Jev model once thresholds are tuned against it |

Do not configure a shared download directory.

## Setup

1. Pick a unique `cdp-chrome.port` and `profile_dir` for this OS user.
2. `plugins/chrome/skills/cdp-chrome/scripts/doctor.sh` checks config, port ownership and profile consistency. If it reports another user or profile on the port, change the port.
3. `plugins/chrome/skills/cdp-chrome/scripts/start.sh` starts GUI Chrome on that profile.
4. Log in to the needed sites by hand; sessions persist.

MCP: installing the `chrome` plugin registers the `cdp-chrome` server through the plugin-local `.mcp.json`, whose launcher reads the config, validates the listener, and runs `chrome-devtools-mcp --browserUrl http://127.0.0.1:<port>`. Do not add a duplicate project-level `.mcp.json` for the same server.

## Target binding

This skill is satisfied only when operating the configured endpoint. `scripts/page.mjs` reads the config and connects there directly. Similar tools (`mcp__chrome_devtools__*`, Playwright, Puppeteer, browser-use) are not substitutes unless proven to use `http://127.0.0.1:<port>`; they can silently attach to a different browser. If the `cdp-chrome` MCP namespace is missing, run `doctor.sh`, then use `curl -s http://127.0.0.1:<port>/json/list` and `page.mjs`; do not guess with another tool.

Findings about cookies, extensions, WebRTC, DNS or policy observed here prove only this profile. Record binary, user-data-dir and Profile Path from `chrome://version` before drawing conclusions; keep such validation read-only.

## Agent rules

1. **Operate pages with `scripts/page.mjs`** (run it with no arguments for usage). It works only on tabs it opened, which also keeps you off other sessions' tabs. Never launch your own Chrome (`start.sh` if the instance is down), never clear cookies, change settings or install extensions. Parallel agents run in separate processes.
2. **With a TypeSafe key: `page.mjs run <url> "<goal>" --value name=text …` is the default, and you stay outside the loop.** Pass the user's goal whole, every part in order, one sentence per part; supply every literal it may need to type as a `--value` (it never writes text). Jev picks operation and element step by step (~0.4 s/step), follows new tabs, and leaves the tab open. On `DONE`, verify the outcome, not the path: one `eval` of the fields you care about on that tab, extract, `close` (or `--close`). On a hand-back (`UNSURE`, `BLOCKED`, `STUCK`, `NEEDS_CONFIRMATION`, `MAX_STEPS`), do the one step it could not (CAPTCHA, login, a confirmation the user asked for) and `run <target> "<same goal>"`; it continues with the history. Do not click through the middle of a task yourself or open extra tabs to re-check.
3. **Without a key: drive the numbered table yourself.** `open` prints the elements in the viewport; `click` / `type` / `select` / `key` / `scroll` act on numbers with real input events; `do` batches several actions when they are all on the current table. Each action prints the refreshed table and returns `FAILED` (never a silent success) when an element is gone or covered. See `references/page-interaction.md`.
4. **Look only when the table cannot tell you.** `page.mjs shot` or `take_screenshot` (~1K vision tokens) for canvas, image-only controls, layout. Never `take_snapshot` to understand a page: its tree costs 10K–540K chars.
5. **Extract with one capped expression.** `page.mjs eval` truncates at 8K chars; in MCP `evaluate_script`, truncate in-script. Never return unbounded DOM or page text.
6. **Keep private pages away from `run`.** Each step sends the element table and visible text to the TypeSafe API.

## Execution log

`page.mjs` appends one JSON line per command to a monthly file in `log_dir`: time, command, tab, site (origin + path), target element, `ok`/`failed` with reason, duration, table size; for `run`, the chosen operation with Jev's confidence and latency. It never records typed text, `eval` code or output, or page text. Use it to find failing sites and widgets and to tune `run` thresholds.

## Quick checks

```bash
PORT=$(python3 -c "import json,os;p=os.path.join(os.environ.get('APPDATA',os.path.expanduser('~/.config')),'steroids.json');print((json.load(open(p)) if os.path.exists(p) else {}).get('cdp-chrome',{}).get('port',9224))")
curl -s "http://127.0.0.1:$PORT/json/version"
```

Red flags: another OS user on the port, process args without the configured `--user-data-dir`, `--enable-automation`, `--remote-debugging-pipe`, temp `puppeteer_dev_chrome_profile-*`, unexpected logouts. Stop and fix config or registration.
