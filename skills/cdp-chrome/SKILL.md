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

This Skill defines the architecture, the rules every agent must follow, and includes all scripts needed for setup. It is written to work for both Claude-style and Codex-style local agent setups.

## Why This Exists

### The Automation Detection Problem

CDP tools (chrome-devtools-mcp, Playwright, Puppeteer) default to launching Chrome with `--enable-automation`. This flag sets `navigator.webdriver = true`, which social media platforms (X/Twitter, Reddit, etc.) detect to block bot logins.

Patching `navigator.webdriver` via JavaScript is fragile — platforms have multi-layered detection (CDP protocol fingerprints, Puppeteer-injected globals like `window.cdc_*`, timing anomalies). The only robust solution is a **genuinely normal Chrome** launched without any automation flags.

### The Multi-Instance Problem

When multiple skills/agents each launch their own Chrome, ports collide, sessions conflict, and login state fragments across disposable profiles. A single shared instance eliminates all of this.

### chrome-devtools-mcp Specifically

The chrome-devtools-mcp MCP server (providing `mcp__chrome-devtools__*` tools) defaults to spawning its own Chrome via Puppeteer with `--enable-automation` and `--remote-debugging-pipe`.

That default is unacceptable for this workflow:
- it creates a disposable profile instead of using the shared logged-in profile
- it loses saved sessions and cookies
- it is trivially identifiable as automation

The MCP server must therefore be configured to connect to the existing shared instance with `--browserUrl=http://127.0.0.1:<port>` rather than launching a browser.

## Architecture

```
~/.config/cdp-chrome/
  port              # TCP port (one line, e.g. "9224")
  profile/          # --user-data-dir (persistent login sessions)
  start.sh          # Launch script — deployed from this Skill's scripts/

Agent config (tooling-specific, but always user-scope/global)
  Claude-style config:
    chrome-devtools → --browserUrl=http://127.0.0.1:<port>
  Codex-style config:
    mcp_servers.chrome-devtools.args = ["--browserUrl", "http://127.0.0.1:<port>", ...]
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

3. Register chrome-devtools at **user scope** so it applies in every directory.

   Claude-style example:

   ```bash
   claude mcp add chrome-devtools -s user -- npx chrome-devtools-mcp@latest --browserUrl=http://127.0.0.1:9224
   ```

   Codex-style example:

   ```toml
   [mcp_servers.chrome-devtools]
   command = "chrome-devtools-mcp"
   args = ["--browserUrl", "http://127.0.0.1:9224", "--no-usage-statistics"]
   ```

   Adjust the port if it differs from 9224. Do NOT create a project-level `./.mcp.json` for this — that only activates when the cwd matches one project.

4. Run the start script, then manually log in to needed sites (X/Twitter, Reddit, etc.) in the Chrome window. Sessions persist in the profile.

5. Ensure the user's global agent instructions reference this Skill as mandatory for all browser operations.

## Rules for Agents

### 1. Never launch your own Chrome

Do not start a new Chrome process. Do not use Puppeteer's `launch()` or Playwright's `chromium.launch()`. The shared instance is already running.

### 2. Connect, don't launch

- **chrome-devtools-mcp tools** (`mcp__chrome-devtools__*`): should already be configured at user scope to use `--browserUrl=http://127.0.0.1:<port>`. Just use them.
- **Direct CDP access** (fallback): read port from `~/.config/cdp-chrome/port`, use `http://127.0.0.1:<port>/json/...`

### 3. Clean up your tabs

Open tabs for your task, close them when done. Other agents share the same browser.

### 4. Don't modify the browser profile

Don't clear cookies, change settings, or install extensions. The profile contains login sessions that other tasks depend on.

### 5. Check before assuming it's running

If chrome-devtools-mcp tools fail to connect, check if the shared Chrome is running. If not, run the start script at `~/.config/cdp-chrome/start.sh`.

### 6. Verify that you are on the correct instance

Do not assume that successful browser automation means the configuration is correct. A misconfigured MCP can silently launch a wrong browser that looks usable but has the wrong profile.

Minimum checks:
- Confirm the shared debugging endpoint is live:
  - `cat ~/.config/cdp-chrome/port`
  - `curl http://127.0.0.1:<port>/json/version`
- Confirm the real shared browser has tabs or login state you expect:
  - `curl http://127.0.0.1:<port>/json/list`
- If using process inspection, the correct shared instance should show:
  - `--remote-debugging-port=<port>`
  - `--user-data-dir=$HOME/.config/cdp-chrome/profile`

Red flags that mean you are on the wrong browser:
- process args contain `--enable-automation`
- process args contain `--remote-debugging-pipe`
- `user-data-dir` points to a temp directory such as `puppeteer_dev_chrome_profile-*`
- sites that should be logged in are unexpectedly logged out

If any red flag appears, stop browsing and fix the MCP registration before proceeding.

### 7. Common misconfiguration: Codex launching Puppeteer anyway

In Codex-style setups, a common failure mode is:

- the shared Chrome on `127.0.0.1:<port>` is running correctly
- but the Codex MCP entry for `chrome-devtools` does not include `--browserUrl`
- so `chrome-devtools-mcp` launches its own temporary Chrome anyway

Typical bad config:

```toml
[mcp_servers.chrome-devtools]
command = "chrome-devtools-mcp"
args = ["--isolated", "--no-usage-statistics"]
```

Typical good config:

```toml
[mcp_servers.chrome-devtools]
command = "chrome-devtools-mcp"
args = ["--browserUrl", "http://127.0.0.1:9224", "--no-usage-statistics"]
```

If you fix the config, restart the agent session before trusting `mcp__chrome_devtools__*` again. Existing sessions may remain attached to the wrong browser until restarted.

### 8. MCP config changes require session restart

**This is critical and easy to forget.** When you update the MCP registration (e.g., adding `--browserUrl`), the running MCP server process still uses the old config. The fix only takes effect after restarting the Claude Code / Codex session. In the meantime, `mcp__chrome-devtools__*` tools will silently connect to (or launch) the wrong browser.

**If you cannot restart the session** (e.g., other agents sharing the session, or mid-task), bypass the MCP tools and use the CDP HTTP API directly:

```bash
# Read the port
PORT=$(cat ~/.config/cdp-chrome/port)

# Open a new tab
curl -s -X PUT "http://127.0.0.1:$PORT/json/new?https://example.com"

# List open tabs
curl -s "http://127.0.0.1:$PORT/json/list"

# Close a tab by ID
curl -s -X PUT "http://127.0.0.1:$PORT/json/close/$TAB_ID"
```

This connects to the correct shared Chrome regardless of MCP state.

## Ensuring Compliance

This Skill is **mandatory, not optional**. Every agent that touches a browser must follow it.

### Global agent instructions

The user's global instructions should contain a directive like:

> **凡是需要有头（GUI）Chrome 的操作，必须遵循 `steroids:cdp-chrome` Skill** — 先 invoke 该 Skill 再开始操作。禁止自行启动 Chrome。

This ensures any agent reading global instructions knows to load and follow this Skill before performing browser operations.

### For Skill/Agent Authors

When writing a skill or agent that needs browser access:
- Do NOT include Chrome launch logic — depend on the shared instance
- State the dependency: "Requires CDP Chrome shared instance (see `steroids:cdp-chrome`)"
- Use chrome-devtools-mcp tools or direct CDP API — both route to the shared instance

### For Herald and Other Automated Agents

Agents with scheduled tasks (news collection, social media scraping) should verify Chrome is reachable at task start. If not, run the start script. Do not fall back to launching a separate Chrome.
