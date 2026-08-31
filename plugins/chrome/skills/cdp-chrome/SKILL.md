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

**Scope:** Optional implementation of the abstract `headed-browser` capability. Do not force this plugin when the user already has an equivalent provider.

## Why This Exists

`chrome-devtools-mcp` can launch Chrome with automation flags such as `--enable-automation`, which sets `navigator.webdriver = true`. This plugin instead connects MCP to a normal GUI Chrome process with a persistent profile.

The process is shared across agents **for the same OS user only**. On multi-user machines, every OS user should configure a different port/profile so agents fail fast instead of connecting to another user's Chrome.

## Tier First: Most Browsing Tasks Should NOT Use This Skill

cdp-chrome is the single shared headed instance, reserved for tasks that need one of its unique capabilities: **logged-in sessions, anti-bot/real-browser fingerprint, or a GUI the user watches**. Before using it, name which of these the task needs; if you can't, use the lightweight tier, picking whatever the current environment provides:

1. `agent-browser` CLI (if installed): on-demand, no MCP, headless by default; use `--session <unique-name>` for full isolation from other agents; covers screenshots, text extraction, snapshots, click/fill, and eval. Run `agent-browser skills get core` for usage first.
2. Other one-shot headless means: an isolated devtools MCP instance already registered in the environment, or one-shot invocations like `chrome --headless=new --screenshot=... / --dump-dom <URL>` (with a temporary `--user-data-dir`).

## Config

steroids config file:
- macOS/Linux: `~/.config/steroids.json`
- Windows: `%APPDATA%\steroids.json`
- shell form: `${APPDATA:-$HOME/.config}/steroids.json`

Default config:

```json
{ "cdp-chrome": { "port": 9224, "profile_dir": "~/.config/cdp-chrome/profile" } }
```

Existing configs with only `port` still work; `profile_dir` defaults to `~/.config/cdp-chrome/profile`. Do not configure a shared download directory; Chrome default downloads are left alone.

## Setup / Doctor

1. Choose a unique `cdp-chrome.port` and `profile_dir` for this OS user in the steroids config file.
2. Run the plugin script:

   ```bash
   plugins/chrome/skills/cdp-chrome/scripts/doctor.sh
   ```

   It verifies current-user config, port ownership, and Chrome profile consistency. If it reports another OS user or another profile on the port, choose a different `cdp-chrome.port` and rerun it.

3. Start Chrome:

   ```bash
   plugins/chrome/skills/cdp-chrome/scripts/start.sh
   ```

   The script creates `profile_dir`, refuses occupied/wrong-user/wrong-profile listeners on macOS, and starts normal GUI Chrome without `--enable-automation`.

4. Log in manually to needed sites. Sessions persist in the configured profile.

## MCP Registration

Claude Code and Codex: installing the `chrome` plugin provides `cdp-chrome` through plugin-local `.mcp.json`. Claude Code documents `${CLAUDE_PLUGIN_ROOT}` for plugin MCP paths; current Codex plugin loading has been verified to start plugin MCP entries with `cwd: "."` at the installed plugin root. The shared `.mcp.json` uses a small shell launcher to support both cases, then runs `skills/cdp-chrome/scripts/mcp-launcher.sh`; that launcher reads the current user's config, validates an existing listener when possible, then execs:

```bash
npx -y chrome-devtools-mcp@latest --browserUrl http://127.0.0.1:<port> --no-usage-statistics \
  --no-category-performance --no-category-emulation --no-category-network
```

Hermes: plugin-local MCP config is not auto-loaded. Register an equivalent `mcp_servers.cdp-chrome` manually and point it at this plugin's `mcp-launcher.sh` or at the same `chrome-devtools-mcp` command with your configured port. Restart/reload MCP after config changes.

Do not create a duplicate project-level `./.mcp.json` for the same server; duplicate MCP definitions can connect to different ports.

## Target Binding

This skill is only satisfied when the agent is operating on the configured shared CDP endpoint. Similar-looking tools such as `mcp__chrome_devtools__*`, Playwright, Puppeteer, or browser-use are not substitutes unless they are explicitly registered as the `cdp-chrome` server for this plugin and proven to use the configured `http://127.0.0.1:<port>` endpoint. They can silently attach to a different browser or target, even when their API is based on Chrome DevTools.

If the expected `cdp-chrome` MCP namespace is not exposed, do not guess with another browser tool. First run `doctor.sh`, then use the configured endpoint directly:

```bash
curl -s "http://127.0.0.1:<port>/json/list"
```

Pick the intended target from `/json/list` and operate through its `webSocketDebuggerUrl`, or report that the `cdp-chrome` MCP namespace is missing. A page list from any other tool is not proof that this skill is attached to the shared Chrome.

## Profile-scoped Validation

CDP Chrome uses its own `profile_dir`. Cookies, extensions, Preferences, WebRTC, or DNS results observed in this instance only prove that profile; likewise `doctor.sh` only proves the port/process/user-data-dir binding is correct — not that the user's daily Chrome is fixed.

Before drawing conclusions about browser policy, WebRTC, DNS, extensions, or login state, record the current binary, user-data-dir, and the Profile Path from `chrome://version`, and state the scope of the conclusion explicitly. Profile preferences must not be extrapolated to other profiles; only managed policies shown in `chrome://policy` with Source=`Platform`, Level=`Mandatory`, Status=`OK` apply across profiles, and even those must be retested in the actually affected browser and a fresh incognito window. Keep validation read-only — do not use CDP Chrome to casually change profile settings.

## Agent Rules

1. Use only MCP tools from server name `cdp-chrome` (`mcp__cdp-chrome__*` in Claude/Codex, `mcp_cdp_chrome_*` style in Hermes), or the direct configured CDP endpoint fallback above. Do not fall back to other Chrome/Playwright/Puppeteer MCP tools; they may launch automated Chrome or attach to a different Chrome target.
2. Never launch your own Chrome. Use `start.sh` if the configured instance is not running.
3. Before browser work, run `doctor.sh` when setup changed or when connection errors occur.
4. Only operate on pages you created: open your own via `new_page`, remember its target, and close it when done. `list_pages` lists tabs from **all sessions** — never `select_page`/`close_page` a page you did not create, and never guess tab ownership by title or index.
5. Do not clear cookies, change profile settings, install extensions, or modify the browser profile.
6. Parallel agents should run in separate agent processes. A single MCP process can have global selected-page state even though Chrome tabs have independent CDP target IDs.
7. **Understand pages visually first.** Before interacting with a complex or unknown page, call `take_screenshot` (~800–1,600 vision tokens) to see the layout. Do NOT call `take_snapshot` for this purpose — its A11Y text tree costs 10K–540K chars (2.5K–135K text tokens) on complex pages and often exceeds tool limits. After the screenshot gives you spatial understanding, use `evaluate_script` for precise extraction/action.
8. **Reserve `take_snapshot` for simple pages only.** Login forms, settings panels, confirmation dialogs — pages where the A11Y tree is expected to be < 5K chars. For anything else, screenshot + evaluate_script is both cheaper and more effective.
9. **Cap `evaluate_script` results.** When writing extraction JS, truncate or paginate output in-script (e.g. `.slice(0, 100)` for arrays, `.slice(0, 8000)` for text). Do not return unbounded DOM content or full page text.

## Quick Checks

```bash
PORT=$(python3 - <<'PY'
import json, os
p=os.path.join(os.environ.get('APPDATA', os.path.join(os.environ['HOME'], '.config')), 'steroids.json')
try:
    print(json.load(open(os.path.expanduser(os.path.expandvars(p)))).get('cdp-chrome', {}).get('port', 9224))
except FileNotFoundError:
    print(9224)
PY
)
curl -s "http://127.0.0.1:$PORT/json/version"
curl -s "http://127.0.0.1:$PORT/json/list"
```

Red flags: another OS user owns the port, process args lack the configured `--user-data-dir`, `--enable-automation`, `--remote-debugging-pipe`, temp `puppeteer_dev_chrome_profile-*`, or unexpected logouts. Stop and fix config/MCP registration.

## Page Interaction

See `references/page-interaction.md` for detailed patterns and examples.

**Tool selection guide:**

| Purpose | Tool | Token cost | Notes |
|------|------|-----------|------|
| Understand page layout | `take_screenshot` | ~800–1,600 vision tokens | First choice for complex/unknown pages |
| Precise extraction/action | `evaluate_script` | ~650 text tokens (controllable) | Workhorse tool |
| Get element UIDs | `take_snapshot` | 2.5K–135K text tokens | Simple pages only |
| Navigation | `navigate_page` | ~190 text tokens | — |
