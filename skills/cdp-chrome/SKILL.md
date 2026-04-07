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

**Scope: This Skill governs all headed (GUI) Chrome usage.** Any task that needs a visible Chrome browser — social media, login-required sites, JS-rendered pages, anti-bot-protected sites — must follow this Skill. Headless browser usage (unit testing your own code, PDF generation) is out of scope.

This Skill defines the architecture, the rules every agent must follow, and includes all scripts needed for setup.

## Why This Exists

### The Automation Detection Problem

CDP tools (chrome-devtools-mcp, Playwright, Puppeteer) default to launching Chrome with `--enable-automation`. This flag sets `navigator.webdriver = true`, which social media platforms (X/Twitter, Reddit, etc.) detect to block bot logins.

Patching `navigator.webdriver` via JavaScript is fragile — platforms have multi-layered detection (CDP protocol fingerprints, Puppeteer-injected globals like `window.cdc_*`, timing anomalies). The only robust solution is a **genuinely normal Chrome** launched without any automation flags.

### The Multi-Instance Problem

When multiple skills/agents each launch their own Chrome, ports collide, sessions conflict, and login state fragments across disposable profiles. A single shared instance eliminates all of this.

### chrome-devtools-mcp Specifically

The chrome-devtools-mcp MCP server (providing `mcp__chrome-devtools__*` tools) defaults to spawning its own Chrome via Puppeteer with `--enable-automation` and `--remote-debugging-pipe`. Our `~/.mcp.json` override makes it connect to the shared clean instance instead via `--browser-url`.

## Architecture

```
~/.config/cdp-chrome/
  port              # TCP port (one line, e.g. "9224")
  profile/          # --user-data-dir (persistent login sessions)
  start.sh          # Launch script — deployed from this Skill's scripts/

~/.mcp.json         # Deployed from this Skill's scripts/
  chrome-devtools → --browser-url=http://127.0.0.1:<port>
```

**Key properties of the shared Chrome:**
- GUI mode (not headless) — avoids headless detection
- No `--enable-automation` — `navigator.webdriver` stays `false`
- Persistent profile — login sessions survive across restarts
- Single port from config — all agents read the same file

## Setup (New Machine)

For a fresh environment, deploy the scripts from this Skill:

1. Create config directory and set a port:
   - `mkdir -p ~/.config/cdp-chrome`
   - Write a port number (e.g. `9224`) to `~/.config/cdp-chrome/port`

2. Deploy the launch script from `scripts/start.sh` in this Skill directory to `~/.config/cdp-chrome/start.sh`. Make it executable.

3. Deploy `scripts/mcp.json` from this Skill directory to `~/.mcp.json`. Adjust the port in `--browser-url` to match the port file if it differs from 9224.

4. Run the start script, then manually log in to needed sites (X/Twitter, Reddit, etc.) in the Chrome window. Sessions persist in the profile.

5. Ensure the user's global `~/.claude/CLAUDE.md` references this Skill as mandatory for all browser operations.

## Rules for Agents

### 1. Never launch your own Chrome

Do not start a new Chrome process. Do not use Puppeteer's `launch()` or Playwright's `chromium.launch()`. The shared instance is already running.

### 2. Connect, don't launch

- **chrome-devtools-mcp tools** (`mcp__chrome-devtools__*`): already configured via `~/.mcp.json`. Just use them.
- **Direct CDP access** (fallback): read port from `~/.config/cdp-chrome/port`, use `http://127.0.0.1:<port>/json/...`

### 3. Clean up your tabs

Open tabs for your task, close them when done. Other agents share the same browser.

### 4. Don't modify the browser profile

Don't clear cookies, change settings, or install extensions. The profile contains login sessions that other tasks depend on.

### 5. Check before assuming it's running

If chrome-devtools-mcp tools fail to connect, check if the shared Chrome is running. If not, run the start script at `~/.config/cdp-chrome/start.sh`.

## Ensuring Compliance

This Skill is **mandatory, not optional**. Every agent that touches a browser must follow it.

### Global CLAUDE.md

The user's `~/.claude/CLAUDE.md` must contain a directive like:

> **凡是需要有头（GUI）Chrome 的操作，必须遵循 `steroids:cdp-chrome` Skill** — 先 invoke 该 Skill 再开始操作。禁止自行启动 Chrome。

This ensures any agent reading global instructions knows to load and follow this Skill before performing browser operations.

### For Skill/Agent Authors

When writing a skill or agent that needs browser access:
- Do NOT include Chrome launch logic — depend on the shared instance
- State the dependency: "Requires CDP Chrome shared instance (see `steroids:cdp-chrome`)"
- Use chrome-devtools-mcp tools or direct CDP API — both route to the shared instance

### For Herald and Other Automated Agents

Agents with scheduled tasks (news collection, social media scraping) should verify Chrome is reachable at task start. If not, run the start script. Do not fall back to launching a separate Chrome.
