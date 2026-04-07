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

## 方案：统一 CDP Chrome 实例

### 核心原则

1. **一个 Chrome 进程服务所有 CDP 需求**——不同 skill/agent 通过不同 tab 并行操作（一个 Chrome 可同时开多个 tab，每个 tab 有独立的 targetId 和 WebSocket 连接，天然支持并行）
2. **端口不硬编码**——统一配置文件，所有 skill/agent 从同一位置读取
3. **GUI 模式**——避免平台 bot 检测
4. **独立 profile**——与用户日常 Chrome 隔离，不影响日常浏览

### 配置结构

```
~/.config/cdp-chrome/
├── port              # 端口号（一行纯文本，如 "9224"）
└── profile/          # Chrome --user-data-dir（登录态持久化）
```

### 启动方式

启动脚本位于 `~/.config/cdp-chrome/start.sh`：

```bash
~/.config/cdp-chrome/start.sh
```

脚本会检查是否已在运行，未运行则以 GUI 模式启动 Chrome。关键点：**不带 `--enable-automation` 标志**，避免社交媒体平台（X/Twitter 等）的反自动化检测。

### chrome-devtools-mcp 集成

chrome-devtools-mcp（提供 `mcp__chrome-devtools__*` 系列工具）默认行为是自己启动一个带 `--enable-automation` 的 Chrome 实例。这会导致：
- `navigator.webdriver = true`
- X/Twitter 等平台拒绝登录
- 无法使用持久化的登录态

**解决方案**：通过 `~/.mcp.json` 配置 chrome-devtools-mcp 连接已有的共享 Chrome 实例，而非自己启动：

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": [
        "chrome-devtools-mcp@latest",
        "--browser-url=http://127.0.0.1:9224"
      ]
    }
  }
}
```

这样所有 `mcp__chrome-devtools__*` 工具都通过共享的干净 Chrome 操作，享受同样的持久登录态。

### 操作方式

两种等价的操作方式：

**方式 1：chrome-devtools-mcp 工具**（推荐，通过 Claude Code 插件自动可用）

使用 `mcp__chrome-devtools__navigate_page`、`mcp__chrome-devtools__evaluate_script` 等工具操作页面。

**方式 2：直连 CDP HTTP API**（备选，用于 chrome-devtools-mcp 不可用时）

```bash
PORT=$(cat ~/.config/cdp-chrome/port)

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

1. [x] 创建配置目录和 port 文件（`~/.config/cdp-chrome/`）
2. [x] 编写启动脚本 `~/.config/cdp-chrome/start.sh`（读配置、检查运行状态、按需启动，不带 `--enable-automation`）
3. [x] 配置 `~/.mcp.json`，让 chrome-devtools-mcp 通过 `--browser-url` 连接共享实例（而非自己启动带 automation 标志的 Chrome）
4. [x] 首次使用时 GUI 模式启动，手动登录所需站点，cookie 持久化在 profile 中
5. [ ] 各 skill/agent 的 Chrome 启动逻辑改为调用共享启动脚本或直接读配置

### 使用流程

1. 运行 `~/.config/cdp-chrome/start.sh` 启动共享 Chrome（或设为 login item 开机自启）
2. 首次需要手动在 Chrome 窗口中登录 X/Twitter、Reddit 等站点
3. 启动 Claude Code 会话，chrome-devtools-mcp 自动连接共享实例
4. 后续会话复用同一 Chrome 进程和登录态

## 开放问题

- [x] 是否需要多 profile 隔离？结论：不需要，不同域名的 cookie 天然隔离
- [ ] 是否向 web-access skill 提 PR？列表见上方"建议向 web-access skill 提的改进"
- [ ] 是否将 Chrome 启动脚本设为 macOS login item（开机自启）
