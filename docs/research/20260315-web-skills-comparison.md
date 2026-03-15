# Web 采集 Skill 对比报告

> 创建：2026-03-15

**BLUF**：三个 Skill 定位互补——last30days 是多平台研究引擎（重代码，弱扩展），Agent-Reach 是工具安装器（广覆盖，浅方法论），eze web-access 是分层浏览方法论（轻量，无平台深度）。没有一个同时具备深度平台知识 + 分层路由 + Session 管理。

对比三个已有的 Web 采集相关 Skill，为 [scraper 方案](../tech/20260315-scraper-scheme.md)设计提供参考。

**怎么选**：

| 我想… | 用这个 |
|-------|--------|
| 调研一个话题，看各平台上大家在聊什么 | **last30days** — 一条命令搜 11 个平台出综合简报 |
| 给新机器装好所有采集工具 | **Agent-Reach** — `agent-reach install` 一键装 16 个平台的工具 |
| 打开一个网页/抓一个页面的内容 | **eze web-access** — 自动选最轻的方式（Jina → WebFetch → CDP） |

## 一、定位对比

| 维度 | **[last30days](https://github.com/mvanhorn/last30days-skill)** | **[Agent-Reach](https://github.com/Panniantong/Agent-Reach)** | **[eze web-access](https://github.com/eze-is/eze-skills/tree/main/web-access)** |
|------|---------------|-----------------|-------------------|
| **一句话定位** | 多平台趋势研究引擎 | 一键安装 Agent 上网工具集 | 分层浏览方法论 |
| **本质** | Python 研究脚本（~16K 行） | 安装器 + 健康检查 CLI | 方法论 SKILL.md（242 行）+ 4 个 shell 脚本 |
| **核心价值** | 搜 11 个平台 → 评分排序 → 综合简报 | 一条命令装好 16 个平台的采集工具 | 教 Agent 选对工具、像人一样浏览 |
| **用户交互** | 每次查询：输入主题 → 输出研报 | 一次性安装 + `doctor` 诊断 | 无直接交互，Agent 遵循方法论 |
| **方法论深度** | 高（评分算法、查询理解、去重） | 中（平台指南 + 反检测提示） | 高（分层原则、不降级规则、登录检测） |
| **平台专用知识** | 浅（每个平台 = 一个 API adapter） | 中（安装指南 + 反检测提示） | 浅（只标记"需要 CDP"，无具体踩坑经验） |
| **代码复杂度** | 极高（37 个 Python 模块） | 中（15 个 channel checker） | 极低（4 个 shell 脚本） |
| **可扩展性** | 差（加一个平台需改 7 个现有文件） | 好（加一个 channel = 一个 Python 文件） | 好（加一个平台 = 补充 SKILL.md） |

## 二、采集模式覆盖

| 采集模式 | last30days | Agent-Reach | eze web-access |
|---------|-----------|-------------|----------------|
| WebSearch (SERP) | 内置（Brave/Parallel/OpenRouter） | Exa Search (via mcporter) | ✅ 第 1 层 |
| WebFetch (HTTP GET) | -- | -- | ✅ 第 2b 层 |
| Jina Reader (Puppeteer → Markdown) | -- | ✅ 通用网页 | ✅ 第 2 层（默认） |
| Agent Browser Playwright 原生 | -- | -- | -- |
| Agent Browser CDP Chrome | -- | -- | ✅ 第 3 层 |
| 逆向 API/CLI（Bird、xreach 等） | ✅ 主力 | ✅ 安装工具 | -- |
| 第三方 SaaS（ScrapeCreators 等） | ✅ 多平台 | -- | -- |
| 反检测浏览器（Camoufox） | -- | ✅ 微信公众号 | -- |

## 三、平台覆盖

| 平台 | last30days | Agent-Reach | eze web-access |
|------|-----------|-------------|----------------|
| **X/Twitter** | Bird GraphQL + cookie | xreach CLI（Bird fork）+ cookie | 通用 CDP |
| **小红书** | xiaohongshu-mcp REST API（轻量搜索） | xiaohongshu-mcp (Docker) | 提到需 CDP，无具体方案 |
| **Reddit** | ScrapeCreators SaaS | Exa + 公开 JSON API | 通用 CDP |
| **YouTube** | yt-dlp 本地 CLI | yt-dlp 本地 CLI | 通用 CDP |
| **TikTok** | ScrapeCreators SaaS | -- | 通用 CDP |
| **Instagram** | ScrapeCreators SaaS | -- | 通用 CDP |
| **微信公众号** | -- | Camoufox + miku_ai（搜狗） | 提到需 CDP |
| **微博** | -- | mcp-server-weibo | -- |
| **抖音** | -- | douyin-mcp-server | -- |
| **Bilibili** | -- | yt-dlp + cookie | -- |
| **HackerNews** | Algolia 公开 API | -- | -- |
| **Bluesky** | AT Protocol 官方 API | -- | -- |
| **Polymarket** | Gamma 公开 API | -- | -- |
| **Truth Social** | Mastodon API | -- | -- |
| **LinkedIn** | -- | linkedin-scraper-mcp | -- |
| **RSS** | -- | feedparser | -- |
| **播客** | -- | groq-whisper + ffmpeg | -- |
| **通用网页** | Brave/Parallel/OpenRouter 搜索 | Jina Reader | 4 层递进 |

## 四、工具分类：直接抓 vs 走 SaaS

| 分类 | 工具 | 覆盖平台 | 费用 |
|------|------|---------|------|
| **直接抓（本地）** | Bird / xreach | X/Twitter | 免费（cookie auth） |
| | yt-dlp | YouTube/Bilibili/1800+ | 免费 |
| | xiaohongshu-mcp | 小红书 | 免费（Docker + cookie） |
| | douyin-mcp-server | 抖音 | 免费（无需登录） |
| | mcp-server-weibo | 微博 | 免费 |
| | Camoufox + miku_ai | 微信公众号 | 免费 |
| | Agent Browser CDP | 任意平台 | 免费 |
| | PRAW | Reddit | 免费（官方 API） |
| **走 SaaS** | ScrapeCreators | Reddit/X/TikTok/Instagram | 付费 |
| | Jina Reader | 通用网页 | 免费 20 RPM |
| | Exa Search | 语义搜索 | 免费 via mcporter |
| | Algolia HN | HackerNews | 免费 |
| | Brave Search | 通用搜索 | 付费 |
| | Claude WebSearch | 通用 SERP | $0.01/次 |

## 五、Session/Profile 管理对比

仅 eze web-access 有完整的 Profile 管理方案：

| 维度 | eze web-access |
|------|---------------|
| Profile 目录 | `~/.claude/browser-profile/` |
| 并行端口 | 9222-9299 |
| 并行 Profile | `~/.claude/browser-profile-{PORT}/` |
| 克隆方式 | rsync 选择性排除（锁文件 + 缓存） |
| 快照机制 | 关闭 9222 时自动快照，并行端口从快照克隆 |
| 排除列表 | `SingletonLock`, `SingletonCookie`, `SingletonSocket`, `*.lock`, `Default/Cache/`, `Default/Code Cache/`, `Default/GPUCache/`, `Default/Service Worker/CacheStorage/`, `ShaderCache/`, `GrShaderCache/` |

last30days 和 Agent-Reach 均不涉及 Browser Profile 管理。

## 六、关键技术细节

### Bird CLI / xreach（X/Twitter 逆向 API）

- 逆向 x.com 网页版内部 GraphQL API（非官方公开 API）
- 从本机浏览器 cookie 存储读取 `auth_token` + `ct0`
- 伪装为 Twitter 官方网页客户端（相同 Bearer token、User-Agent、feature flags）
- 动态破解部署后变化的 GraphQL query ID（下载 JS bundle 正则提取）
- xreach 是 Bird 的 fork（Bird 停更后维护）
- **风险**：违反 ToS，用真实账号 session，有封号可能

### Camoufox（反检测浏览器）

- 基于 Firefox 魔改（非 Chromium），C++ 引擎层面拦截浏览器指纹
- 比 Playwright/Puppeteer 的 JS 层 stealth 补丁更难被检测
- Agent-Reach 用于微信公众号：miku_ai 搜索（搜狗）→ Camoufox 读取文章全文

### xiaohongshu-mcp（小红书 REST API）

- `xpzouying/xiaohongshu-mcp`（GitHub 9K+ stars），Go 编写
- Docker 运行，需手动登录获取 cookie
- 仅支持搜索和基础信息获取（标题、描述、互动数据）
- 不支持深度采集（评论详情、作者主页等）

### Jina Reader

- 免费 SaaS：`curl https://r.jina.ai/{url}` → 干净 Markdown
- 底层 Puppeteer 渲染 + Readability 算法提取正文
- 能处理 JS 渲染，但对反爬严格的站点无效
- 限流 20 RPM

### last30days 评分算法

```
X engagement = 0.55*log1p(likes) + 0.25*log1p(reposts) + 0.15*log1p(replies) + 0.05*log1p(quotes)
overall = 0.45*relevance + 0.25*recency + 0.30*engagement
```

- 通用多因子评分（relevance + recency + engagement），各平台可定制 engagement 权重
- 纯 Python stdlib，约 1,050 行，零外部依赖，可独立提取
