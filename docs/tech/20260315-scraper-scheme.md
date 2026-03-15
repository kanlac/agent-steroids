# Scraper Skill 方案

> 状态：调研完成，待启动开发
> 创建：2026-03-15
> 参考：[同类 skill 调研报告](../research/20260315-web-skills-comparison.md)

## 当前策略

先试用现有 Skill（last30days、Agent-Reach、eze web-access），积累实际使用经验。出现以下情况时启动本 Skill 开发：

- **平台专用知识缺失**：用现有 Skill 采集某个平台（如 X、搜狗）时反复踩坑，需要积累 Negatives 和平台专用方法（类似小红书 Skill 的深度）
- **模式选择低效**：Agent 在 WebFetch / Jina / Playwright / CDP 之间选择不当，需要一个统一的分层路由指导
- **Session/Profile 管理混乱**：多个 Claude Code 实例并行采集时出现 Profile 冲突、session 占用等问题，需要标准化管理流程
- **跨平台采集需求常态化**：不再是偶尔采集某一个平台，而是经常需要在一次任务中跨多个平台获取信息
- **现有 Skill 能力分散难以组合**：比如 Bird 评分算法在 last30days 里、Camoufox 在 Agent-Reach 里、分层路由在 eze web-access 里，需要从多个 Skill 中拼凑能力，不如统一到一个 Skill

## 目标

设计一个通用的 `scraper` Skill，让 Claude Code 能从各种平台（社交媒体、JS 渲染页面等）获取信息。解决 WebFetch 无法处理 JS 渲染页面、社交平台反爬等问题。

## Skill 架构

### 分层设计

| 层级 | 位置 | 职责 |
|------|------|------|
| **通用层** `scraper` | `agent-steroids/skills/` | 采集模式选择、Session/Profile 管理、通用反检测、各平台采集方法 |
| **业务层**（各项目自定义） | 项目 `.claude/skills/` | 输出格式、入库逻辑、业务特定配置（如 JSON 输出 + SQLite 入库） |

通用层包含所有平台的采集方法论（含小红书精简版），业务层只补充项目特有的需求。

### 目录结构

```
agent-steroids/skills/scraper/
├── SKILL.md                     # 主文档：模式选择路由 + 通用知识
├── scripts/
│   └── manage-profile.sh        # Profile 克隆与管理
└── references/
    ├── mode-playwright.md       # Agent Browser Playwright 原生
    ├── mode-cdp-chrome.md       # Agent Browser CDP Chrome
    ├── platform-xhs.md          # 小红书（精简版）
    ├── platform-x.md            # X/Twitter（验证后填充）
    ├── platform-sogou.md        # 搜狗/微信公众号（验证后填充）
    └── ...
```

### SKILL.md 职责

1. 接收用户意图（"采集 XX 平台的 YY 数据"）
2. 判断平台 → 已知平台查对应指南；未知平台按模式选择流程判断
3. 路由到对应的方法文档
4. 管理 session/profile 分配（检测占用、选择空闲资源）

## 采集模式

从轻到重排列（详见[对比报告](../research/20260315-web-skills-comparison.md)）：

| 模式 | 说明 | JS 渲染 | 适用场景 |
|------|------|---------|---------|
| **A. WebSearch** | SERP 搜索引擎摘要 | N/A | 发现信息源、快速了解 |
| **B. WebFetch** | HTTP GET 纯文本 | 不支持 | SSR 页面、结构化 meta 提取 |
| **C. Jina Reader** | Puppeteer 渲染 → Markdown | ✅ | 文章/博客/文档，JS 页面轻量方案 |
| **D. Agent Browser Playwright** | 内置 Chromium，`--session` 隔离 | ✅ | 需要交互、反 bot 不严 |
| **E. Agent Browser CDP Chrome** | 真实 Chrome + Profile | ✅ | 反 bot 严格的社交平台 |
| **F. 逆向 API/CLI** | Bird/xreach 等本地工具 | N/A | 有成熟工具的平台 |
| **G. 反检测浏览器** | Camoufox 等 | ✅ | CDP Chrome 仍被检测的场景 |
| **H. 第三方 SaaS** | ScrapeCreators 等 | N/A | 不想维护逆向工程 |

**选择原则**：能用轻的就不用重的。已知平台查指南，未知平台按 A → B → C → D → E 顺序尝试。

**不降级原则**（参考 eze web-access）：确定进入某一层级后，不回退到更轻的模式。

### 模式选择流程

```
目标 URL/平台
  │
  ├─ 已知平台？→ 查平台指南，用推荐模式
  │
  └─ 未知平台 →
       ├─ 1. WebFetch → 有效内容？ → YES → 模式 B
       ├─ 2. Jina Reader → 有效内容？ → YES → 模式 C
       ├─ 3. Agent Browser Playwright → 能打开？能提取？
       │     ├─ YES + 不需登录 → 模式 D
       │     ├─ YES + 需登录 → state save/load 够？→ YES → 模式 D + state
       │     └─ NO（被检测）→ 继续
       └─ 4. Agent Browser CDP Chrome → 模式 E
```

## Session 与 Profile 管理

### Session 命名

Session 是**平台无关**的——一个 session/profile 可持有多个平台的登录态。

```bash
agent-browser --session worker-1 ...
agent-browser --session worker-2 ...
```

### Profile 目录

```
~/.agent-browser/
├── profiles/
│   ├── main/              # 主 profile：手动登录所有社交平台
│   ├── worker-1/          # 从 main 克隆
│   └── worker-2/          # 从 main 克隆
└── sessions/              # agent-browser 自动管理
```

- 一个 main profile 存所有平台登录态
- 并行时 rsync 克隆（排除锁文件和缓存，参考 eze web-access 方案）
- 克隆的 profile 保留不删，下次复用

### Profile 克隆

采纳 eze web-access 的选择性排除方案：

```bash
rsync -a --delete \
  --exclude='SingletonLock' --exclude='SingletonCookie' --exclude='SingletonSocket' \
  --exclude='*.lock' \
  --exclude='Default/Cache/' --exclude='Default/Code Cache/' \
  --exclude='Default/GPUCache/' --exclude='Default/Service Worker/CacheStorage/' \
  --exclude='ShaderCache/' --exclude='GrShaderCache/' \
  "$SOURCE_PROFILE/" "$TARGET_PROFILE/"
```

### 占用检测

agent-browser 内置检测，不需要外部状态管理：

```bash
agent-browser session list --json    # Playwright session
lsof -i :9222                        # CDP 端口
```

### 并行采集

典型场景是**不同平台并行**（同 IP 同平台多会话有风控风险）：

```
Claude Code #1 (小红书)          Claude Code #2 (X/Twitter)
    │                                │
    ▼                                ▼
CDP Chrome (port 9222)           Playwright 原生 (--session worker-2)
profile: worker-1                state: loaded
```

## 已知平台策略

### 小红书 — 模式 E (CDP Chrome)，已验证

- 反 bot 极严，必须真实 Chrome + Profile
- 大量踩坑经验（xsec_token、DOM-only 提取、CSS selector 点击等）
- 完整方法详见 `references/platform-xhs.md`

### X/Twitter — 待验证

候选：模式 F (Bird/xreach CLI) 或模式 E (CDP Chrome)

### 搜狗/微信公众号 — 待验证

候选：模式 B (WebFetch) 或模式 C (Jina) 或模式 D (Playwright)；可能需要模式 G (Camoufox) 读取文章全文

### 通用 JS 渲染页面 — 先试模式 C (Jina)，不行再 D (Playwright)

## 可复用组件

| 来源 | 组件 | 用途 |
|------|------|------|
| eze web-access | 分层方法论 + ensure-browser.sh + close-browser.sh | SKILL.md 骨架 + Profile 管理脚本 |
| last30days | Bird 搜索（~2,500 行）+ 评分算法（~1,050 行） | X 采集 + 通用结果排序 |
| Agent-Reach | 平台→工具映射、反检测提示 | 参考信息 |
| 现有 XHS Skill | 精简版采集方法 + Negatives | platform-xhs.md |
