---
name: cdp-chrome
description: |
  Shared headed Chrome instance for browser automation. MANDATORY for any scenario requiring
  a visible (GUI/headed) Chrome browser. This includes but is not limited to:
  - Social media access: browsing X/Twitter, Reddit, Instagram, posting, reading feeds, verifying tweet dates
  - News/article verification: checking publish dates, fetching JS-rendered pages, bypassing paywalls
  - Websites requiring login state: any site where persistent sessions are needed
  - Anti-bot-protected sites: sites that detect headless/automation browsers
  - Web form interaction: filling forms, clicking buttons on real websites
  - Visual page inspection: taking screenshots, checking layouts on live sites
  NOT required for: headless testing of your own code, PDF generation, Playwright/Puppeteer unit tests.
  Trigger phrases: "open browser", "check website", "scrape page", "navigate to",
  "browser automation", "CDP Chrome", "chrome-devtools", "visit URL",
  "check Twitter/X", "check Reddit", "verify article date", "login to site",
  "browse", "open page", "access website", "fetch page with JS".
---

# CDP Chrome: Shared Headed Browser Instance

**Scope:** All headed (GUI) Chrome usage must follow this Skill. Headless testing/PDF generation is out of scope.

## Why This Exists

CDP tools default to `--enable-automation`, setting `navigator.webdriver = true` — detected by social media platforms. JS patching is fragile (multi-layered detection). The only robust solution: a genuinely normal Chrome without automation flags.

Multiple agents each launching Chrome causes port collisions, session conflicts, fragmented login state. A single shared instance eliminates all of this.

chrome-devtools-mcp specifically must be configured with `--browserUrl=http://127.0.0.1:<port>` to connect to the shared instance, not launch its own Puppeteer Chrome.

## Architecture

```
Config file:
  macOS/Linux: ~/.config/steroids.json
  Windows:     %APPDATA%\steroids.json
  Content:     { "cdp-chrome": { "port": 9224 } }

~/.config/cdp-chrome/
  profile/          # --user-data-dir (persistent login sessions)
  start.sh          # Launch script — deployed from this Skill's scripts/
```

Key properties: GUI mode, no `--enable-automation`, persistent profile, single port from config.

## Setup (New Machine)

1. Set port in config file:
   ```json
   { "cdp-chrome": { "port": 9224 } }
   ```
   Then: `mkdir -p ~/.config/cdp-chrome`

2. Deploy `scripts/start.sh` from this Skill to `~/.config/cdp-chrome/start.sh`. Make executable.

3. Register chrome-devtools at **user scope**:
   ```bash
   claude mcp add chrome-devtools -s user -- npx chrome-devtools-mcp@latest --browserUrl=http://127.0.0.1:9224
   ```
   Do NOT create project-level `./.mcp.json` for this.

4. Run start script, manually log in to needed sites. Sessions persist in profile.

## Rules for Agents

### 1. Never launch your own Chrome

Do not start a new Chrome process. Do not use Puppeteer's `launch()` or Playwright's `chromium.launch()`.

### 2. Connect, don't launch

- **chrome-devtools-mcp tools** (`mcp__chrome-devtools__*`): already configured at user scope.
- **Direct CDP access** (fallback): read port from config, use `http://127.0.0.1:<port>/json/...`

### 3. Clean up your tabs

Open tabs for your task, close them when done. Other agents share the same browser.

### 4. Don't modify the browser profile

Don't clear cookies, change settings, or install extensions.

### 5. Check before assuming it's running

If tools fail to connect, run `~/.config/cdp-chrome/start.sh`.

### 6. Verify correct instance

Check: `curl http://127.0.0.1:<port>/json/version` and `/json/list`.

Red flags (wrong browser): `--enable-automation` in process args, `--remote-debugging-pipe`, temp `user-data-dir` like `puppeteer_dev_chrome_profile-*`, unexpected logouts. Stop and fix MCP registration if any appear.

Common Codex misconfiguration: MCP entry missing `--browserUrl` → chrome-devtools-mcp launches its own Chrome silently.

### 7. MCP config changes require session restart

The running MCP process uses old config until restart. If you cannot restart, bypass MCP and use CDP HTTP API directly:

```bash
CONFIG="${APPDATA:-$HOME/.config}/steroids.json"  # Windows: %APPDATA%, others: ~/.config
PORT=$(python3 -c "import json,os; print(json.load(open(os.path.expandvars('$CONFIG')))['cdp-chrome']['port'])")
curl -s -X PUT "http://127.0.0.1:$PORT/json/new?https://example.com"  # open tab
curl -s "http://127.0.0.1:$PORT/json/list"                             # list tabs
curl -s -X PUT "http://127.0.0.1:$PORT/json/close/$TAB_ID"            # close tab
```

## Ensuring Compliance

This Skill is **mandatory**. Global agent instructions must mandate it for all browser operations. Skill/agent authors must not include Chrome launch logic — only state dependency on `steroids:cdp-chrome`. Scheduled agents should verify Chrome is reachable at task start.
