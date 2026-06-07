---
name: cdp-chrome
description: |
  Optional per-OS-user headed Chrome provider for browser automation. Use when
  an environment chooses cdp-chrome for visible GUI Chrome: social media,
  JS-rendered pages, logged-in sites, anti-bot pages, forms, screenshots, and
  live site inspection. Not required when an equivalent provider exists.
---

# CDP Chrome: Per-User Headed Browser Provider

**Scope:** Optional implementation of the abstract `headed-browser` capability. Do not force this plugin when the user already has an equivalent provider.

## Why This Exists

`chrome-devtools-mcp` can launch Chrome with automation flags such as `--enable-automation`, which sets `navigator.webdriver = true`. This plugin instead connects MCP to a normal GUI Chrome process with a persistent profile.

The process is shared across agents **for the same OS user only**. On multi-user machines, every OS user should configure a different port/profile so agents fail fast instead of connecting to another user's Chrome.

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
npx -y chrome-devtools-mcp@latest --browserUrl http://127.0.0.1:<port> --no-usage-statistics
```

Hermes: plugin-local MCP config is not auto-loaded. Register an equivalent `mcp_servers.cdp-chrome` manually and point it at this plugin's `mcp-launcher.sh` or at the same `chrome-devtools-mcp` command with your configured port. Restart/reload MCP after config changes.

Do not create a duplicate project-level `./.mcp.json` for the same server; duplicate MCP definitions can connect to different ports.

## Agent Rules

1. Use only MCP tools from server name `cdp-chrome` (`mcp__cdp-chrome__*` in Claude/Codex, `mcp_cdp_chrome_*` style in Hermes). Do not fall back to other Chrome/Playwright/Puppeteer MCP tools; they may launch automated Chrome.
2. Never launch your own Chrome. Use `start.sh` if the configured instance is not running.
3. Before browser work, run `doctor.sh` when setup changed or when connection errors occur.
4. Open tabs for your task and close them when done. Do not touch other agents' tabs.
5. Do not clear cookies, change profile settings, install extensions, or modify the browser profile.
6. Parallel agents should run in separate agent processes. A single MCP process can have global selected-page state even though Chrome tabs have independent CDP target IDs.

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

Prefer `evaluate_script` for precise extraction/actions. Avoid relying on full accessibility snapshots for complex pages; they can exceed tool limits. See `references/page-interaction.md`.
