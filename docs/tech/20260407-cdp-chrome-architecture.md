# CDP Chrome 统一架构

> 状态：已实施  
> 日期：2026-04-07

## 背景

Claude Code 插件生态中，多个 skill/agent 需要通过 Chrome DevTools Protocol (CDP) 操控浏览器：采集社交媒体内容、核实文章发布时间、自动化网页操作等。

当前存在以下问题：

### 问题 1：多实例端口冲突

各 skill 独立启动 Chrome 实例，端口硬编码在各自脚本中。当新 skill 选择的端口恰好在其他 skill 的扫描列表中，会产生误连。

### 问题 2：web-access skill 的 CDP Proxy 端口发现有缺陷

详见 [web-access CDP Proxy 端口发现问题](./20260407-web-access-cdp-proxy-issues.md)。

核心结论：Proxy 的端口检测用 TCP 探测而非 HTTP 检测，会被日常 Chrome 的 DevToolsActivePort 端口骗过（TCP 通但 CDP API 返回 404），进入死循环。且 Chrome 136+ 默认 profile 已不支持 `--remote-debugging-port`，skill "直连日常 Chrome" 的前提已失效。

### 问题 3：Headless 检测

Reddit 等平台检测 headless Chrome 特征（`navigator.webdriver=true`、HeadlessChrome UA），触发 CAPTCHA 或封号。需要 GUI 模式运行。

## 方案：每 OS 用户一个 CDP Chrome 实例

### 核心原则

1. **每个 OS 用户一个 Chrome 进程服务本用户的 CDP 需求**——不同 skill/agent 通过不同 tab 并行操作（一个 Chrome 可同时开多个 tab，每个 tab 有独立的 targetId 和 WebSocket 连接，天然支持并行）
2. **端口和 profile 不硬编码**——统一从当前用户的 steroids 配置文件读取；多用户机器上每个 OS 用户必须选择自己的 `port` 和 `profile_dir`
3. **GUI 模式**——避免平台 bot 检测
4. **独立 profile**——与用户日常 Chrome 隔离，不影响日常浏览
5. **失败优先于误连**——启动脚本和 MCP wrapper 会尽量用 `lsof`/`ps` 校验监听者属于当前 OS 用户，且 Chrome 命令行中的 `--user-data-dir` 与配置一致；macOS 上无法确认时拒绝继续

### 配置结构

steroids 配置文件位置：macOS/Linux 为 `~/.config/steroids.json`，Windows 为 `%APPDATA%\steroids.json`。

```
~/.config/cdp-chrome/
└── profile/          # Chrome --user-data-dir（登录态持久化）

steroids 配置文件
└── { "cdp-chrome": { "port": 9224, "profile_dir": "~/.config/cdp-chrome/profile" } }
```

`port` 默认 `9224`，`profile_dir` 默认 `~/.config/cdp-chrome/profile`。历史配置只有 `port` 也继续可用。不要配置共享下载目录，Chrome downloads 保持默认行为。

### 启动方式

启动脚本位于插件目录 `plugins/chrome/skills/cdp-chrome/scripts/start.sh`，可按需复制或直接运行：

```bash
plugins/chrome/skills/cdp-chrome/scripts/start.sh
```

脚本会读取当前用户 steroids 配置，创建配置的 profile 目录，检查端口是否已被占用。如果端口属于其他 OS 用户，或属于一个 `--user-data-dir` 不匹配的 Chrome，会清晰报错并要求用户在 steroids 配置中选择不同的 `cdp-chrome.port`。未运行则以 GUI 模式启动 Chrome。关键点：**不带 `--enable-automation` 标志**，避免社交媒体平台（X/Twitter 等）的反自动化检测。

新增 `doctor.sh` 用于 setup/runtime 验证：

```bash
plugins/chrome/skills/cdp-chrome/scripts/doctor.sh
```

它会打印当前配置、检查 profile 可创建性、端口 HTTP/CDP 状态、监听进程 owner/profile 是否与当前 OS 用户配置一致，并给出换端口/停冲突进程等 remediation。

### chrome-devtools-mcp 集成

chrome-devtools-mcp（Claude Code/Codex 中暴露为 `mcp__cdp-chrome__*` 系列工具；Hermes 使用 `mcp_<server>_<tool>` 命名）默认行为是自己启动一个带 `--enable-automation` 的 Chrome 实例。这会导致：
- `navigator.webdriver = true`
- X/Twitter 等平台拒绝登录
- 无法使用持久化的登录态

**解决方案**：Chrome 插件在 Claude Code / Codex 中通过插件根目录 `.mcp.json` 提供 `cdp-chrome` MCP wrapper，让 wrapper 读取当前用户配置、验证监听者，然后让 chrome-devtools-mcp 连接已有的本用户 Chrome 实例，而非自己启动。Hermes 支持 MCP，但当前是 `mcp_servers` 配置驱动，不会从 plugin shim 自动加载 `.mcp.json`：

```json
{
	  "mcpServers": {
	    "cdp-chrome": {
	      "command": "bash",
	      "args": [
	        "-c",
	        "PLUGIN_ROOT=\"${CLAUDE_PLUGIN_ROOT:-${CODEX_PLUGIN_ROOT:-}}\"; if [ -z \"$PLUGIN_ROOT\" ] && [ -x \"./skills/cdp-chrome/scripts/mcp-launcher.sh\" ]; then PLUGIN_ROOT=\"$PWD\"; fi; if [ -z \"$PLUGIN_ROOT\" ]; then echo 'ERROR: plugin root not found for cdp-chrome MCP launcher' >&2; exit 1; fi; exec \"$PLUGIN_ROOT/skills/cdp-chrome/scripts/mcp-launcher.sh\""
	      ]
	    }
	  }
	}
```

这样所有 `cdp-chrome` MCP 工具都通过当前 OS 用户自己的干净 Chrome 操作，享受同样的持久登录态，并避免静默连接到其他用户/profile。

### 操作方式

两种等价的操作方式：

**方式 1：chrome-devtools-mcp 工具**（推荐；Claude Code/Codex 通过插件自动可用，Hermes 需手动注册 `mcp_servers`）

Claude Code/Codex 使用 `mcp__cdp-chrome__navigate_page`、`mcp__cdp-chrome__evaluate_script` 等工具操作页面；Hermes 使用其 `mcp_<server>_<tool>` 命名下的对应工具。

**方式 2：直连 CDP HTTP API**（备选，用于 chrome-devtools-mcp 不可用时）

```bash
CONFIG="${APPDATA:-$HOME/.config}/steroids.json"
PORT=$(python3 -c "import json,os; print(json.load(open(os.path.expandvars('$CONFIG')))['cdp-chrome']['port'])")

# 创建 tab（Chrome 146+ 需要 PUT）
curl -s -X PUT "http://127.0.0.1:$PORT/json/new"

# 关闭 tab
curl -s -X PUT "http://127.0.0.1:$PORT/json/close/$TARGET_ID"
```

页面内操作通过 WebSocket 发送 CDP 命令（`Page.navigate`、`Runtime.evaluate` 等）。

### 与 web-access skill 的关系

当前绕过 CDP Proxy，直连 CDP HTTP API。web-access skill 的浏览哲学、站点经验、并行分治策略等内容仍然有价值，只是 CDP 连接层绕过了它的 Proxy。

### 建议向 web-access skill 提的改进

详见 [web-access CDP Proxy 端口发现问题](./20260407-web-access-cdp-proxy-issues.md)，该文档可直接作为 PR 附件。

## 实施步骤

1. [x] 创建配置目录和 steroids 配置项（`port` + `profile_dir`，兼容仅配置 `port` 的历史配置）
2. [x] 编写启动脚本 `scripts/start.sh`（读配置、检查 owner/profile、按需启动，不带 `--enable-automation`）
3. [x] 在 Chrome 插件中内置 `.mcp.json`，让 plugin-local wrapper 校验后通过 `--browserUrl` 连接当前 OS 用户实例（而非自己启动带 automation 标志的 Chrome）
4. [x] 增加 `scripts/doctor.sh`，用于 setup/runtime 验证和 remediation 提示
5. [x] 首次使用时 GUI 模式启动，手动登录所需站点，cookie 持久化在 profile 中
6. [ ] 各 skill/agent 的 Chrome 启动逻辑改为调用共享启动脚本或直接读配置

### 使用流程

1. 为当前 OS 用户选择唯一 `cdp-chrome.port/profile_dir`，运行 `doctor.sh` 验证
2. 运行 `scripts/start.sh` 启动共享 Chrome（或设为 login item 开机自启）
3. 首次需要手动在 Chrome 窗口中登录 X/Twitter、Reddit 等站点
4. 启动 Claude Code/Codex 会话，chrome-devtools-mcp 通过 wrapper 自动连接当前用户实例
5. 后续会话复用同一 Chrome 进程和登录态

## 开放问题

- [x] 是否需要多 profile 隔离？结论：不需要，不同域名的 cookie 天然隔离
- [ ] 是否向 web-access skill 提 PR？列表见上方"建议向 web-access skill 提的改进"
- [ ] 是否将 Chrome 启动脚本设为 macOS login item（开机自启）
