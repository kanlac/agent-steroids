---
name: paper-download
description: |
  Use when the user asks to "download a paper", "find a paper",
  "get PDF for DOI", "下载论文", "找论文", "知网下载",
  or mentions academic paper retrieval needs.
version: 0.9.0
user-invocable: true
allowed-tools: Bash, Read, Write, WebFetch
---

# Paper Download Skill

学术论文检索与下载。检索和下载是两个独立阶段，用户没有明确要求下载时只做检索。

## STOP: 使用浏览器前必须先 invoke `steroids:cdp-chrome`

所有浏览器操作均通过该 Skill 提供的共享 Chrome 实例进行。**不得使用其他任何 Chrome/browser MCP 工具。**

## 核心原则

1. **检索和下载分离** — 用户说"找/搜/检索"→ 只做阶段一；用户说"下载/下/get PDF"→ 做阶段一+二。不要自作主张进入下载阶段
2. **检索不回退** — 阶段一只用 CNKI 和 Google Scholar，遇到验证码让用户手动解决后继续，不要因为验证码就放弃该站点转用其他检索方式（如 OpenAlex、CrossRef 等不是检索工具）
3. **确保论文匹配** — 跨源下载时必须用 DOI 或标题+作者校验
4. **永远不主动付费** — 不点击任何付费按钮
5. **逐级升级** — 能用 HTTP 直链就不走浏览器

## Prerequisites

使用浏览器前 invoke `steroids:cdp-chrome`，由该 Skill 负责环境检查与启动。

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
| CNKI 知网 | 检索+下载 | 中文论文检索与下载 | 检索免费无需登录；下载需账号有额度或机构订阅 |
| arXiv | 下载 | CS/ML 预印本 PDF 直链 | `arxiv.org/pdf/{id}.pdf`，无需认证；API 限速 1 req/3s，并发需加 delay |
| Unpaywall API | 辅助 | 查 OA 状态 + 找合法 PDF 直链 | 免费无 key；能区分 gold/hybrid/closed；Sci-Hub 失效后找非 arXiv OA 链接的首选 |
| CrossRef API | 辅助 | 标题 → DOI 查询 | 纯 HTTP，免费无 key，毫秒级 |

### 补充站点

| 站点 | 阶段 | 用途 | 备注 |
|------|------|------|------|
| Sci-Hub | 下载 | 2021 年前非 OA 论文 | 数据库已冻结于 2021 年底，2022+ 论文基本不可用；镜像轮询：se → st → ru |
| Anna's Archive | 下载 | Sci-Hub 失败时的备选 | 覆盖面更广（含书籍）；可达性不稳定，可能需要额外代理配置 |
| LibGen | 下载 | 同上，偏书籍 | 期刊论文覆盖与 Sci-Hub 相近，同样停更于 2021 年前后 |
| PMC | 下载 | 生物医学 OA 论文 | `ncbi.nlm.nih.gov/pmc`，CS 方向基本用不到 |
| OpenAlex | 检索 | 元数据补全、OA 状态批量查询 | Scholar 已覆盖其主要功能，仅在需要批量 API 查询时有用 |
| 期刊官网（MDPI、Springer 等） | 下载 | Gold/Hybrid OA 期刊 PDF | curl 直连常被 bot 检测拦截返回 HTML；应走浏览器 JS fetch |

---

## 阶段一：检索

检索只用 CNKI 和 Google Scholar，不用其他站点替代。遇到验证码是正常的，提示用户在 Chrome 中手动完成，等用户确认后继续——不要放弃该站点。

### Google Scholar（国际论文）

`browser_navigate` → `https://scholar.google.com`，填入关键词/标题。
反爬较严，遇验证码提示用户手动完成，等用户确认后继续检索。右侧 [PDF] 标记即 OA 直链，记录备用。

### CNKI（中文论文）

详细操作流程见 `references/cnki-workflow.md`。
使用高级检索 `https://kns.cnki.net/kns8s/AdvSearch`，支持来源过滤（CSSCI/核心期刊）、多字段组合、框内运算符。
搜索、摘要、关键词、作者等元数据无需登录即可获取（共享 Chrome profile 自带 cookie，通常不会触发验证码）。检索阶段不需要确保已登录。

**遇到安全验证/滑块验证码时**：提示用户在 Chrome 窗口中手动完成，等用户确认后继续。这是知网的正常行为，不是错误，不要因此放弃知网。

### 结果输出

检索完成后**必须**生成一个 Excel 文件（`.xlsx`），不论结果数量多少。字段：

| 列 | 说明 |
|---|---|
| 标题 | 论文标题 |
| 作者 | 第一作者 + et al. |
| 期刊/会议 | 发表来源 |
| 年份 | 发表年份 |
| DOI | 如有 |
| OA 状态 | Open Access / Closed / 未知 |
| 链接 | 论文详情页 URL（知网/Scholar） |
| PDF 直链 | 检索阶段发现的 OA 直链（如有） |
| 摘要 | 如已获取 |

生成后告知用户文件路径，并在终端简要列出前几条结果。检索到此为止——不要自动进入下载阶段，除非用户明确要求了下载。

---

## 阶段二：下载（仅在用户明确要求时执行）

### 批量下载策略

按层级批量处理，逐层收窄：先 Tier 1 处理所有论文，失败的进 Tier 2，仍失败的进 Tier 3。

Tier 2/3 涉及多个站点时，按站点分独立进程并行（遵循 `cdp-chrome` 并行安全规则），进程内串行逐篇处理。多源都成功的论文，对比后保留最优版本。

### 论文匹配校验

跨源下载必须校验：DOI 精确匹配 > 标题相似度 > 标题+作者+年份。

### Tier 1: 直链（URL 模式已知，直接 curl，可并行）

- **arXiv**: `https://arxiv.org/pdf/{id}.pdf`（并发时加 3s delay，遵守限速）
- **Scholar OA 直链**（检索阶段已获取，右侧 [PDF] 标记）
- **Unpaywall OA 直链**: `GET https://api.unpaywall.org/v2/{doi}?email={user_email}` → 取 `best_oa_location.url_for_pdf`

下载：`curl -L -C - --retry 3 -o "{path}" "{url}"`
命名：`作者_短标题_年份.pdf`
校验：文件前 4 字节为 `%PDF`，否则视为失败（期刊官网常返回 HTML，必须校验）

### Tier 2: 解析（给 DOI/URL，提取 PDF 地址）

- **Sci-Hub**（仅 2021 年前论文有效，镜像轮询）: `sci-hub.se/{doi}` → `sci-hub.st/{doi}` → `sci-hub.ru/{doi}` — PDF 在 `<iframe>` / `<embed>` 的 src 中
- **出版商页面**: 解析 DOI 重定向 → 找 PDF 按钮/直链

没有 DOI 时先用 CrossRef API 查询：`GET https://api.crossref.org/works?query.title={title}&rows=3`

### Tier 3: 导航（多步浏览器交互）

共享 Chrome session：
- **期刊官网**（MDPI、Springer 等 Gold/Hybrid OA）：curl 常被 bot 检测拦截，必须走浏览器 JS fetch 下载
- **CNKI 下载**（需 `cnki_auto_download: true` + 已登录 + 账号有下载能力）：仅当账号有实际额度或机构订阅时才有意义，否则跳过。跳转到付费页则**立即停止**
- **Anna's Archive**: `https://annas-archive.org/search?q={query}` → 找下载链接（可达性不稳定）
- **LibGen**: `https://libgen.is/scimag/?q={doi_or_title}` → 点击镜像链接（同 Sci-Hub，停更于 2021 年前后）

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
