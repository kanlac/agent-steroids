# CDP Chrome 统一架构

> 状态：方案设计  
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

```bash
PORT=$(cat ~/.config/cdp-chrome/port)
PROFILE=~/.config/cdp-chrome/profile

# 检查是否已在运行
if ! curl -s --connect-timeout 1 http://127.0.0.1:$PORT/json/version >/dev/null 2>&1; then
  /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=$PORT \
    --user-data-dir=$PROFILE \
    &>/dev/null &
  sleep 3
fi
```

### 操作方式

直连 CDP HTTP API + WebSocket，不经过任何 Proxy 中间层：

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
2. [ ] 编写通用的 `ensure-cdp-chrome.sh` 脚本（读配置、检查运行状态、按需启动），放入 agent-steroids
3. [ ] 各 skill 的 Chrome 启动脚本改为调用通用脚本或直接读配置
4. [ ] 首次使用时 GUI 模式启动，手动登录所需站点，cookie 持久化在 profile 中

## 开放问题

- [ ] 是否需要多 profile 隔离（不同 skill 用不同 Chrome profile）？当前判断：不需要，不同域名的 cookie 天然隔离
- [ ] 是否向 web-access skill 提 PR？列表见上方"建议向 web-access skill 提的改进"
