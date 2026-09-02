# Agent Steroids Plugin Split

## Goal

把原先的单体 `steroids` 拆成少量可独立启用的插件，避免在所有环境里加载 Telegram、Chrome 或 hook。当前只保留三个插件：

1. `steroids` — 主体 Skills 和通用 workflow。
2. `telegram` — Telegram agent 运维、通知 MCP、Telegram hook，并包含 `guard-payload-size`。
3. `chrome` — 可选的共享有头 Chrome provider。

## Design Rules

1. **不要过度拆分**：paper、web clipping 等 workflow 都留在 `steroids`。
2. **浏览器依赖写 capability，不写死 provider**：需要人工接管/登录态/CAPTCHA 时写 `headed-browser`。`chrome/cdp-chrome` 是一个 provider；Codex Chrome plugin 或原生 browser-use 也可以满足。
3. **Telegram 相关能力集中**：Telegram commands、MCP server、time hook、payload guard hook 都在 `telegram`，避免再单独维护 guard 插件。
4. **Codex marketplace 只暴露跨运行时 skill 插件**：当前为 `steroids` 和 `chrome`。`telegram` 保持 Claude Code 专用 marketplace。
5. **Hermes 用根目录 shim 只暴露跨运行时插件**：`agent-steroids/steroids`、`agent-steroids/chrome` 可分别 enable/disable；skill 加载命名空间保持 `steroids:*`、`chrome:*`。`telegram` 是 Claude Code 专用插件，不提供 Hermes shim。

## Plugin Matrix

| Plugin | Runtime | Contents | Hard Dependencies | Soft / Capability Dependencies |
|---|---|---|---|---|
| `steroids` | Claude + Codex + Hermes | `extract-to-md`, `read-book`, `html-to-pdf`, `clipping`, `paper-download`, `/song` | None | `paper-download` / `clipping` may need `headed-browser` |
| `telegram` | Claude Code only | `telegram-agents`, `/tg-*`, `/check-release`, `telegram-notify` MCP, Telegram time hook, `guard-payload-size` hook | Claude Code + official Telegram plugin for channel sessions; Telethon/tmux/launchd for heartbeat workflows | None |
| `chrome` | Claude + Codex + Hermes | `cdp-chrome` per-OS-user headed Chrome provider; bundled MCP wrapper for Claude Code/Codex reads current-user config; Hermes uses config-driven MCP registration | Chrome, `npx`; `mcp_servers` registration for Hermes | Provides `headed-browser`; optional replacement for Codex Chrome plugin/native browser-use |

## Capability Map

```text
headed-browser
├── provided by: chrome / cdp-chrome
├── alternatively: Codex Chrome plugin
└── alternatively: native browser-use / other persistent headed browser tools

telegram-channel
└── provided externally by: telegram@claude-plugins-official

payload-guard
└── provided by: telegram / guard-payload-size

computer-use
└── provided externally by: the user's computer-use MCP setup
```

## Dependency Decisions

### `paper-download` does not hard-depend on `cdp-chrome`

The workflow has three execution tiers:

1. HTTP/API direct download — no browser plugin needed.
2. Headless browser parsing — can be handled by local tooling/subagents.
3. Headed browser with login/CAPTCHA — needs `headed-browser`, but the provider can be `chrome`, Codex Chrome plugin, or another native browser-use integration.

Therefore `paper-download` should check for an already available headed browser provider before suggesting `chrome` installation.

### `clipping` uses the same browser capability pattern

JS-rendered article pages need a headed browser, but `clipping` should not force `cdp-chrome` when the runtime already has an equivalent browser plugin.

### `guard-payload-size` lives in `telegram`

The guard hook is especially useful for long-running Claude Code / Telegram / computer-use sessions, and the user requested not to keep it as a separate plugin. It is configured through `plugins/telegram/hooks/hooks.json` together with Telegram time awareness.

## Installation Manual

All concrete install commands live in the root [`INSTALL.md`](../../INSTALL.md). Keep this design note focused on plugin boundaries and dependency decisions; do not duplicate install commands here.

## Maintenance Checklist

- Keep the Claude marketplace grouped by these plugin names unless the user explicitly asks for another split: `steroids`, `telegram`, `chrome`.
- Keep Codex marketplace and Hermes root shim directories limited to cross-runtime plugins: `steroids`, `chrome`. Do not add `telegram` to Codex/Hermes unless Telegram support is deliberately redesigned for those runtimes.
- Update every changed plugin manifest version, including Hermes `plugin.yaml` shim manifests when their exposed skill set changes.
- Keep README tables grouped by the three canonical plugin directories, while marking runtime coverage accurately.
- Avoid hard dependencies on provider plugins when a capability can be satisfied by another environment.
