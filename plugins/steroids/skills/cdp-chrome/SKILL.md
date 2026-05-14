---
name: cdp-chrome
description: |
  Shared headed Chrome for browser automation. Mandatory for visible GUI Chrome:
  social media, JS-rendered pages, logged-in sites, anti-bot pages, forms,
  screenshots, and live site inspection. Use for requests like open browser,
  check website, scrape page, visit URL, check X/Twitter or Reddit, verify an
  article date, or log in to a site. Not for headless tests, PDF generation, or
  Playwright/Puppeteer unit tests of local code.
---

# CDP Chrome: Shared Headed Browser Instance

**Scope:** All headed (GUI) Chrome usage must follow this Skill. Headless testing/PDF generation is out of scope.

## Why This Exists

CDP tools default to `--enable-automation`, setting `navigator.webdriver = true` — detected by social media platforms. JS patching is fragile (multi-layered detection). The only robust solution: a genuinely normal Chrome without automation flags.

Multiple agents each launching Chrome causes port collisions, session conflicts, fragmented login state. A single shared instance eliminates all of this.

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

Key properties: GUI mode, no `--enable-automation`, persistent profile, single port from config. CDP 每个 tab 有独立的 WebSocket 端点，天然支持多 agent 并行操作不同 tab，无需额外协调。

## Setup (New Machine)

1. Set port in config file:
   ```json
   { "cdp-chrome": { "port": 9224 } }
   ```
   Then: `mkdir -p ~/.config/cdp-chrome`

2. Deploy `scripts/start.sh` from this Skill to `~/.config/cdp-chrome/start.sh`. Make executable.

3. Register MCP — name must be `cdp-chrome`. This is **additive**: do not remove or modify any existing Chrome/browser MCPs the user may already have.

   ```bash
   # Claude Code
   claude mcp add cdp-chrome -s user -- npx chrome-devtools-mcp@latest --browserUrl=http://127.0.0.1:9224
   ```

   其他 agent 用各自的 MCP 配置方式注册同一个 server，关键参数相同：server 为 `chrome-devtools-mcp`，名称为 `cdp-chrome`，必须带 `--browserUrl` 指向共享实例。不带 `--browserUrl` 会自行启动 Chrome，违反共享原则。

   Do NOT create project-level `./.mcp.json` for this.

4. Run start script, manually log in to needed sites. Sessions persist in profile.

## Page Interaction

与页面交互时，优先用 `evaluate_script` 执行 JS 精准提取/操作，不要依赖 `take_snapshot` 的完整 A11Y 树——复杂页面的快照动辄 80K+ 字符，超出工具限制且浪费 token。详见 `references/page-interaction.md`。

## Rules for Agents

### 1. Never launch your own Chrome

Do not start a new Chrome process. Do not use Puppeteer's `launch()` or Playwright's `chromium.launch()`.

### 2. Use ONLY `mcp__cdp-chrome__*` — no other Chrome MCP

**Exclusively use `mcp__cdp-chrome__*` tools.** If you see other Chrome/browser MCP tools in your tool list — such as `mcp__chrome-devtools__*`, `mcp__playwright__*`, `mcp__puppeteer__*`, or any other name — **do NOT use them**. They launch a separate Chrome instance with `--enable-automation` and `--remote-debugging-pipe`, setting `navigator.webdriver = true` and triggering bot detection. The whole point of this Skill is to avoid exactly that.

If `mcp__cdp-chrome__*` tools are not available in your session, **do not fall back to other browser tools**. Instead:
1. Run the setup command to register the MCP: `claude mcp add cdp-chrome -s user -- npx chrome-devtools-mcp@latest --browserUrl=http://127.0.0.1:9224`
2. Tell the user: "MCP 已注册，请在新会话中重新打开以加载工具。"
3. Stop — do not attempt the browser task in the current session.

### 3. Parallel safety

每个 tab 有独立的 CDP WebSocket 端点（按唯一 hex ID 区分），天然支持并行。但 MCP 实例有全局的「当前选中页面」状态——**同进程内多个 subagent 共享 MCP 实例，并行操作浏览器会互相干扰**（select_page 状态冲突）。

安全的并行方式：独立进程（Teammate、多个 `claude -p`、多个 Codex 实例），各自有独立 MCP 实例。

### 4. Clean up your tabs

Open tabs for your task via `new_page`, close them when done. Don't touch other agents' tabs.

### 5. Don't modify the browser profile

Don't clear cookies, change settings, or install extensions.

### 6. Check before assuming it's running

If tools fail to connect, run `~/.config/cdp-chrome/start.sh`.

### 7. Verify correct instance

Check: `curl http://127.0.0.1:<port>/json/version` and `/json/list`.

Red flags (wrong browser): `--enable-automation` in process args, `--remote-debugging-pipe`, temp `user-data-dir` like `puppeteer_dev_chrome_profile-*`, unexpected logouts. Stop and fix MCP registration if any appear.

Common misconfiguration: MCP registered as `chrome-devtools` instead of `cdp-chrome`, or missing `--browserUrl` → launches its own Chrome silently.

### 8. MCP config changes require session restart

The running MCP process uses old config until restart. If you cannot restart, use CDP HTTP API directly as fallback:

```bash
CONFIG="${APPDATA:-$HOME/.config}/steroids.json"
PORT=$(python3 -c "import json,os; print(json.load(open(os.path.expandvars('$CONFIG')))['cdp-chrome']['port'])")
curl -s -X PUT "http://127.0.0.1:$PORT/json/new?https://example.com"  # open tab
curl -s "http://127.0.0.1:$PORT/json/list"                             # list tabs
curl -s -X PUT "http://127.0.0.1:$PORT/json/close/$TAB_ID"            # close tab
```

## Ensuring Compliance

This Skill is **mandatory**. Global agent instructions must mandate it for all browser operations. Skill/agent authors must not include Chrome launch logic — only state dependency on `steroids:cdp-chrome`. Scheduled agents should verify Chrome is reachable at task start.
