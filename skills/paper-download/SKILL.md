---
name: paper-download
description: |
  Use when the user asks to "download a paper", "find a paper",
  "get PDF for DOI", "下载论文", "找论文", "知网下载",
  or mentions academic paper retrieval needs.
version: 0.6.0
user-invocable: true
allowed-tools: Bash, Read, Write, WebFetch
---

# Paper Download Skill

两阶段学术论文下载：先检索收集元数据，再按成本递增逐级下载。

## 核心原则

1. **检索和下载分离** — Scholar/CNKI 用于检索，下载走独立的 Tier 策略
2. **确保论文匹配** — 跨源下载时必须用 DOI 或标题+作者校验
3. **永远不主动付费** — 不点击任何付费按钮
4. **逐级升级** — 能用 HTTP 直链就不走浏览器

## Prerequisites

依赖 `steroids:cdp-chrome` Skill 提供的共享 Chrome 实例：
1. 读取端口：从 steroids 配置文件（macOS/Linux: `~/.config/steroids.json`，Windows: `%APPDATA%\steroids.json`）的 `cdp-chrome.port` 获取
2. 检查是否运行：`curl -s http://127.0.0.1:<port>/json/version`
3. 未运行 → 执行 `~/.config/cdp-chrome/start.sh` 启动
4. 首次使用 → 先 invoke `steroids:cdp-chrome` 完成环境搭建

## 用户配置

路径：macOS/Linux `~/.config/steroids.json`，Windows `%APPDATA%\steroids.json`

```json
{ "paper-download": { "cnki_auto_download": false } }
```

- `cnki_auto_download`: 允许使用知网已有额度自动下载（遇付费页仍停止）

---

## 站点速查表

### 主力站点

| 站点 | 阶段 | 用途 | 备注 |
|------|------|------|------|
| Google Scholar | 检索 | 国际论文检索，顺带给出 OA 直链 | 需浏览器；反爬严，遇验证码要手动 |
| CNKI 知网 | 检索+下载 | 中文论文检索与下载 | 搜索和摘要免费；全文下载需付费或机构订阅 |
| arXiv | 下载 | CS/ML 预印本 PDF 直链 | `arxiv.org/pdf/{id}.pdf`，无需认证 |
| Sci-Hub | 下载 | 非 OA 论文按 DOI 下载 | 覆盖 ~85% 已发表论文；2024+ 新论文收录有延迟 |
| CrossRef API | 辅助 | 标题 → DOI 查询 | 纯 HTTP，免费无 key，毫秒级 |

### 补充站点

| 站点 | 阶段 | 用途 | 备注 |
|------|------|------|------|
| Anna's Archive | 下载 | Sci-Hub 失败时的备选 | 覆盖面更广（含书籍）；速度较慢 |
| LibGen | 下载 | 同上，偏书籍 | 期刊论文覆盖弱于 Sci-Hub |
| PMC | 下载 | 生物医学 OA 论文 | `ncbi.nlm.nih.gov/pmc`，CS 方向基本用不到 |
| OpenAlex | 检索 | 元数据补全、OA 状态查询 | Scholar 已覆盖其主要功能，仅在需要批量 API 查询时有用 |
| 期刊官网 | 下载 | 个别中文 OA 期刊直接下 PDF | 需逐站摸索，如 jsjkx.com |

---

## 阶段一：检索

### Google Scholar（国际论文）

`browser_navigate` → `https://scholar.google.com`，填入关键词/标题。
反爬较严，遇验证码提示用户手动完成。右侧 [PDF] 标记即 OA 直链，优先使用。

### CNKI（中文论文）

详细操作流程见 `references/cnki-workflow.md`。
`browser_navigate` → `https://kns.cnki.net/kns8s/search`，填入关键词。
搜索和摘要免费开放；全文下载需登录——个人账号按篇付费，机构账号通过 IP/VPN 访问（覆盖范围取决于机构采购的子库）。

### 结果输出

- ≤10 条 → 直接展示结构化列表
- \>10 条 → 整理为表格（标题、作者、期刊、年份、DOI、OA、下载状态）

---

## 阶段二：下载（逐级处理）

### 批量下载策略

按层级批量处理，逐层收窄：
1. **Tier 1**: 所有论文并发 curl（10-20 并发），收集失败列表
2. **Tier 2**: 失败的论文批量解析（5-10 并发）
3. **Tier 3**: 仍失败的论文浏览器导航（3-5 tab 并发，每篇独立 tab）

### 论文匹配校验

跨源下载必须校验：DOI 精确匹配 > 标题相似度 > 标题+作者+年份。

### Tier 1: 直链（URL 模式已知，直接 curl，可并行）

- **arXiv**: `https://arxiv.org/pdf/{id}.pdf`
- **Scholar OA 直链**（检索阶段已获取，右侧 [PDF] 标记）

下载：`curl -L -C - --retry 3 -o "{path}" "{url}"`
命名：`作者_短标题_年份.pdf`
校验：文件前 4 字节为 `%PDF`，否则视为失败

### Tier 2: 解析（给 DOI/URL，提取 PDF 地址）

- **Sci-Hub**（镜像轮询）: `sci-hub.se/{doi}` → `sci-hub.st/{doi}` → `sci-hub.ru/{doi}` — PDF 在 `<iframe>` / `<embed>` 的 src 中
- **出版商页面**: 解析 DOI 重定向 → 找 PDF 按钮/直链

没有 DOI 时先用 CrossRef API 查询：`GET https://api.crossref.org/works?query.title={title}&rows=3`

### Tier 3: 导航（多步浏览器交互）

共享 Chrome session，每篇论文在独立 tab 中操作：
- **CNKI 下载**（需 `cnki_auto_download: true` + 已登录 + 有额度）：跳转到付费页则**立即停止**
- **Anna's Archive**: `https://annas-archive.org/search?q={query}` → 找下载链接
- **LibGen**: `https://libgen.is/scimag/?q={doi_or_title}` → 点击镜像链接

### 下载结果标记

| 状态 | 含义 |
|------|------|
| ✓ 已下载 | PDF 已保存 |
| ✗ 需付费 | 附论文页链接 |
| ✗ 需手动 | 验证码等需人工 |
| ✗ 未找到 | 所有渠道均失败 |

---

## Error Escalation

所有无法解决的问题立即用中文告知用户，不静默重试超过一次，不在验证码上循环。
知网遇滑块验证码 → 提示用户在 Chrome 中手动完成；登录失效 → 提示重新登录。
