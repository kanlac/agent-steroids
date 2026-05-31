---
name: cdp-chrome
description: |
  Optional shared headed Chrome provider for browser automation. Use when an
  environment chooses cdp-chrome for visible GUI Chrome: social media,
  JS-rendered pages, logged-in sites, anti-bot pages, forms, screenshots, and
  live site inspection. Not required when an equivalent provider exists (for
  example Codex Chrome plugin or native browser-use). Not for headless tests,
  PDF generation, or Playwright/Puppeteer unit tests of local code.
---

# CDP Chrome: Shared Headed Browser Instance

**Scope:** Optional provider implementation for environments that choose shared GUI Chrome/CDP. If a task only requires the abstract `headed-browser` capability and the user already has another equivalent provider, do not force this plugin.

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

3. MCP registration:

   - Claude Code and Codex: installing the `chrome` plugin provides `cdp-chrome` via the plugin's bundled `.mcp.json`. Start a new session or reload plugins after install/update.
   - Hermes: MCP is supported through `mcp_servers` in `~/.hermes/config.yaml` or `hermes mcp add`, but Hermes plugins do not currently auto-load plugin-local MCP config. Register the server manually. Name must be `cdp-chrome`.
   - Other runtimes: use the runtime's MCP config mechanism with the same command and args. This is **additive**: do not remove or modify any existing Chrome/browser MCPs the user may already have.

   ```yaml
   mcp_servers:
     cdp-chrome:
       command: "npx"
       args:
         - "-y"
         - "chrome-devtools-mcp@latest"
         - "--browserUrl"
         - "http://127.0.0.1:9224"
         - "--no-usage-statistics"
   ```

   其他 agent 用各自的 MCP 配置方式注册同一个 server，关键参数相同：server 为 `chrome-devtools-mcp`，名称为 `cdp-chrome`，必须带 `--browserUrl` 指向共享实例。不带 `--browserUrl` 会自行启动 Chrome，违反共享原则。

   Do NOT create project-level `./.mcp.json` for this. Claude Code/Codex plugin installs already carry the plugin-local `.mcp.json`; adding a duplicate user/project MCP can create conflicting `cdp-chrome` servers.

4. Run start script, manually log in to needed sites. Sessions persist in profile.

## Page Interaction

与页面交互时，优先用 `evaluate_script` 执行 JS 精准提取/操作，不要依赖 `take_snapshot` 的完整 A11Y 树——复杂页面的快照动辄 80K+ 字符，超出工具限制且浪费 token。详见 `references/page-interaction.md`。

## Rules for Agents

### 1. Never launch your own Chrome

Do not start a new Chrome process. Do not use Puppeteer's `launch()` or Playwright's `chromium.launch()`.

### 2. Use ONLY the `cdp-chrome` MCP tools — no other Chrome MCP

**Exclusively use tools from the MCP server named `cdp-chrome`.** Claude Code and Codex expose them as `mcp__cdp-chrome__*`; Hermes uses its `mcp_<server>_<tool>` naming, so expect `mcp_cdp_chrome_*`. If you see other Chrome/browser MCP tools in your tool list — such as `mcp__chrome-devtools__*`, `mcp__playwright__*`, `mcp__puppeteer__*`, or any other name — **do NOT use them**. They launch a separate Chrome instance with `--enable-automation` and `--remote-debugging-pipe`, setting `navigator.webdriver = true` and triggering bot detection. The whole point of this Skill is to avoid exactly that.

If the runtime's `cdp-chrome` MCP tools are not available in your session, **do not fall back to other browser tools**. Instead:
1. Confirm the `chrome` plugin is installed and enabled. In Claude Code, inspect `/plugin` or `claude plugin details chrome`; in Codex, inspect the plugin directory or `codex plugin list`.
2. For Claude Code/Codex, start a new session or reload plugins so the bundled `.mcp.json` is loaded.
3. For Hermes or another runtime without plugin-bundled MCP support, register `cdp-chrome` manually as described in Setup, then restart or reload MCP.
4. Stop — do not attempt the browser task in the current session.

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

Common misconfiguration: MCP registered as `chrome-devtools` instead of `cdp-chrome`, missing `--browserUrl`, or plugin/user MCP duplicates with different ports → launches its own Chrome silently or connects to the wrong instance.

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

This Skill is the implementation guide for the optional `chrome` provider. Global/project instructions should require the abstract `headed-browser` capability for GUI browser tasks, not a hard dependency on this plugin. Skill/agent authors should say “requires a headed browser provider”; list `chrome` / `cdp-chrome` as one supported provider when a shared Chrome profile is desired. Scheduled agents should verify their chosen browser provider is reachable at task start.
