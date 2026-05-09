# Stealth Browser 调研：CDP 自动化指纹与反检测方案

> 调研结论：当前 chrome-devtools-mcp 会设置 `navigator.webdriver = true`，但绝大多数网站（包括知网、学术数据库、新闻站）不检测此标志。只有接入了 Cloudflare Turnstile、DataDome 等反 bot 服务的网站才会受影响。当前方案继续可用，遇到具体被拦截场景再针对性解决。

## 问题背景

chrome-devtools-mcp 内部使用 Puppeteer 连接 Chrome，Puppeteer 在 `connect()` 时调用 `Runtime.enable` CDP 命令，这会导致 Chrome 设置 `navigator.webdriver = true`。同时浏览器顶部会显示 "Chrome is being controlled by automated test software" 信息栏。

我们的共享 Chrome 启动时没有 `--enable-automation` 标志，浏览器本身是干净的——问题出在连接它的客户端库。

## 尝试过的方案（均失败）

| 方案 | 结果 |
|---|---|
| `--disable-blink-features=AutomationControlled` | Chrome 147 报 "unsupported command-line flag"，`navigator.webdriver` 仍为 true |
| `--load-extension` 加载反检测扩展 | Chrome 147 静默忽略，扩展不加载 |
| `Page.addScriptToEvaluateOnNewDocument` 从外部 CDP session 注入 | Per-session 隔离，不影响 MCP 的 Puppeteer session |
| `Emulation.setAutomationOverride({enabled: false})` | 同样 per-session 隔离 |

根因：`Runtime.enable` 的副作用是 per-CDP-session 的，从外部 session 无法覆盖 Puppeteer session 内的状态。chrome-devtools-mcp 官方明确拒绝添加 stealth 功能（GitHub issue #553）。

## 主流 Stealth 项目对比

### Tier 1：高 Star（5000+）

| 项目 | Stars | 语言 | 反检测方式 | 能连已有 Chrome | 维护状态 |
|---|---|---|---|---|---|
| undetected-chromedriver | 12.6k | Python | 修补 chromedriver 二进制 + JS 注入 | 否 | 活跃 |
| camoufox | 8.1k | Python | Firefox C++ 源码级修改 | 否（Firefox） | 活跃 |
| puppeteer-extra-stealth | 7.3k | JS | 16 个 JS 注入模块 + `--disable-blink-features` | 是（connect 模式） | 已停更 2 年 |

### Tier 2：中 Star（1000-5000）

| 项目 | Stars | 语言 | 反检测方式 | 能连已有 Chrome | 维护状态 |
|---|---|---|---|---|---|
| nodriver | 4.2k | Python | 纯 CDP，不用 WebDriver 协议，不调 `Runtime.enable` | 是 | 活跃 |
| patchright | 3.1k | TS+Py | 修补 Playwright 源码移除 `Runtime.enable` | 是 | 活跃 |
| rebrowser-patches | 1.3k | JS | 修补 Puppeteer/Playwright，3 种 Runtime.enable 替代模式 | 是 | 活跃 |

### MCP 封装

| 项目 | Stars | 底层 | 能连已有 Chrome | 评估 |
|---|---|---|---|---|
| patchright-mcp | 16 | patchright (Playwright 补丁) | 是（`--cdp-endpoint`） | 落后上游 7 版本，维护堪忧 |
| stealth-browser-mcp | 631 | nodriver | **否**（总是启动新实例） | 96 工具但不支持共享 Chrome，有 `exec()` 安全风险 |

### 非 MCP 工具

| 项目 | Stars | 类型 | 评估 |
|---|---|---|---|
| agent-browser (Vercel Labs) | 32k | Rust CLI | 纯 Rust CDP，支持 `--cdp` 连接已有 Chrome。但源码确认 `enable_domains()` 硬编码调用 `Runtime.enable`，**同样触发 `navigator.webdriver = true`** |

## 反检测技术路线分类

1. **补丁路线**（patchright、rebrowser）：修改 Playwright/Puppeteer 源码移除 `Runtime.enable`。有效但需跟踪上游版本
2. **协议回避路线**（nodriver）：直接用 CDP WebSocket，精确控制启用哪些 domain，不调用 `Runtime.enable`。架构级安全
3. **JS 注入路线**（puppeteer-extra-stealth）：事后注入 JS 覆盖 `navigator.webdriver`。已过时，现代反 bot 可检测注入痕迹
4. **浏览器修改路线**（camoufox、CloakBrowser）：修改浏览器源码。最彻底但维护成本极高

## 实际影响评估

**`navigator.webdriver = true` 不等于被封。** 网站检测自动化需要专门的反 bot SDK，大多数网站没有部署：

- **不受影响**：学术数据库（知网、Google Scholar）、新闻网站、政府网站、大多数电商、一般 Web 应用
- **可能受影响**：Cloudflare 重度防护的站点、部分社交媒体敏感接口（登录/发帖 API）、票务/抢购系统
- **确定受影响**：专门的反爬服务保护的站点（DataDome、PerimeterX、Akamai Bot Manager）

即便受影响，`navigator.webdriver` 也只是众多信号之一（还有 TLS 指纹、鼠标轨迹、Canvas/WebGL 指纹、HTTP header 顺序等），单一信号通常不直接触发封锁。

## 如果未来需要解决

优先级排序：

1. **patchright-mcp**：最快落地，`claude mcp add cdp-stealth -s user -- npx patchright-mcp@latest --cdp-endpoint http://127.0.0.1:9224`，与现有 cdp-chrome 并存
2. **自建 nodriver MCP**：架构最干净，~1300 行代码，一天工作量。注意 nodriver 是 AGPL 许可

## agent-browser 补充评估（2026-05-09）

**定位**：AI coding agent 的浏览器自动化 CLI，非 MCP。通过 Bash 工具调用，daemon 架构维持状态。

**优势**：命令丰富度远超 chrome-devtools-mcp（batch 批量执行、annotated screenshot、react tree inspect、state save/load、cookie/storage 管理、network route 拦截、viewport/device/geo 模拟等）。Accessibility snapshot 带 `@eN` 元素引用，可直接用于后续交互。

**CDP 模式**：`agent-browser --cdp 9224 snapshot` 连接已有 Chrome。daemon per-session 隔离（`--session name`）。但 `enable_domains()` 硬编码 `Runtime.enable` + `Network.enable` + `Page.enable` + `Target.setAutoAttach`，与 Puppeteer 行为相同。

**与 MCP 的对比**：MCP 工具是 LLM 的一等公民（结构化输入输出）；agent-browser 需要 LLM 组装 shell 命令 + 解析文本输出，多一层间接性。但 `--json` 模式和 `batch` 命令可以缓解。

**结论**：功能维度优秀，反检测维度与现有方案无差异。如果不考虑反检测，它是 chrome-devtools-mcp 的有力替代（更丰富的工具集、无需 MCP 协议、Rust 性能）
