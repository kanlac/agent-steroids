---
name: paper-download
description: |
  Use when the user asks to "download a paper", "find a paper",
  "get PDF for DOI", "下载论文", "找论文", "知网下载",
  or mentions academic paper retrieval needs.
version: 1.0.0
user-invocable: true
allowed-tools: Bash, Read, Write, WebFetch
---

# Paper Download Skill

学术论文检索与下载。检索和下载是两个独立阶段，用户没有明确要求下载时只做检索。

## Prerequisites

检索阶段使用 Google Scholar 和 CNKI（均为 Tier 3），开始前先 invoke `steroids:cdp-chrome` 启动共享 Chrome。

## 核心原则

1. **检索和下载分离** — 用户说"找/搜/检索"→ 只做阶段一；用户说"下载/下/get PDF"→ 做阶段一+二。不要自作主张进入下载阶段
2. **检索不回退** — 阶段一只用 CNKI 和 Google Scholar，遇到验证码让用户手动解决后继续，不要因为验证码就放弃该站点转用其他检索方式（如 OpenAlex、CrossRef 等不是检索工具）
3. **确保论文匹配** — 跨源下载必须校验：DOI 精确匹配 > 标题相似度 ≥ 0.4 > 弃用。永远不要无校验取 CrossRef top-1
4. **永远不主动付费** — 不点击任何付费按钮
5. **逐级升级** — 能用 HTTP 直链就不走浏览器

## 用户配置

路径：macOS/Linux `~/.config/steroids.json`，Windows `%APPDATA%\steroids.json`

```json
{ "paper-download": { "cnki_auto_download": false } }
```

- `cnki_auto_download`: 允许使用知网已有额度自动下载（遇付费页仍停止）

---

## 三层执行环境

下载站点按执行环境分层。Agent 根据 Tier 选择调用方式，逐层升级（1→2→3），不跳级也不回退。

| Tier | 执行环境 | 适用场景 | 并行 |
|---|---|---|---|
| 1 | HTTP（curl / API） | URL 已知、无 JS 渲染、无反爬 | 可并行，同域名限速 |
| 2 | Headless 浏览器 | 需 JS 渲染或轻度反爬，不需登录态 | subagent 各起实例并行 |
| 3 | 共享 headed Chrome（`mcp__cdp-chrome__*`） | 需登录态 / 需用户解 CAPTCHA | 串行（共享单实例），同站点批量复用会话。使用前 invoke `steroids:cdp-chrome` |

---

## 站点速查表

### 主力站点

| 站点 | 阶段 | Tier | 用途 | 备注 |
|------|------|:---:|------|------|
| Google Scholar | 检索 | 3 | 国际论文检索，顺带给出 OA 直链 | 反爬严，遇验证码要手动 |
| CNKI 知网 | 检索+下载 | 3 | 中文论文检索与下载 | 检索免费；下载需账号额度 |
| arXiv | 下载 | 1 | CS/ML/物理/数学预印本 | `arxiv.org/pdf/{id}.pdf`；API 限速 1 req/3s |
| Unpaywall API | 辅助 | — | 查 OA 状态 + 找 PDF 直链 | 免费无 key；区分 gold/hybrid/closed |
| CrossRef API | 辅助 | — | 标题 → DOI 查询 | 免费无 key，毫秒级 |

### 补充站点

| 站点 | 阶段 | Tier | 用途 | 备注 |
|------|------|:---:|------|------|
| Sci-Hub | 下载 | 2 | ≤2021 年非 OA 论文 | **≥2022 直接跳过**；镜像：se → st → ru |
| Anna's Archive | 下载 | 2 | Sci-Hub 备选 | ≤2021；可达性不稳定 |
| LibGen | 下载 | 2 | 同上，偏书籍 | 同 Sci-Hub 停更于 2021 |
| PMC | 下载 | 1 | 生物医学 OA 论文 | CS 方向基本用不到 |
| 期刊官网 | 下载 | 2-3 | OA 期刊 PDF | 轻防护 Tier 2；ScienceDirect 等重防护 Tier 3 |
| OpenAlex | 辅助 | — | 元数据补全、批量 OA 查询 | 全文搜索噪声大，不做检索主源 |

---

## 阶段一：检索

检索只用 CNKI 和 Google Scholar，不用其他站点替代。遇到验证码是正常的，提示用户在 Chrome 中手动完成，等用户确认后继续——不要放弃该站点。

### Google Scholar（国际论文）

`browser_navigate` → `https://scholar.google.com`，填入关键词/标题。
反爬较严，遇验证码提示用户手动完成，等用户确认后继续检索。同一会话内 reCAPTCHA 触发 3 次以上，说明代理节点 IP 信用低——停止让用户解，建议换节点/区域后重试。右侧 [PDF] 标记即 OA 直链，记录备用。

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

### 输出目录

每次下载创建独立批次目录：`batch_<主题>_<YYYY-MM-DD>/`，内含 `pdfs/`（交付物）和 `_workspace/`（中间脚本、日志、快照）。报告 xlsx 放批次目录顶层。

### OA 分流（下载前必做）

下载前先用 Unpaywall 批量查有 DOI 论文的 OA 状态，按结果预分流到对应 Tier，避免盲试：

- **OA 有直链**（gold/green）→ Tier 1
- **非 OA + CS/物理/数学** → 先用 arXiv API 查预印本（标题/DOI 反查，相似度 ≥ 0.4），命中则 Tier 1
- **非 OA + ≤2021** → Tier 2（Sci-Hub）
- **非 OA + ≥2022** → **跳过 Sci-Hub/LibGen/Anna's Archive**（已停更），直接标记「需付费」

预分流后，Tier 1 先批量处理，失败的降级到 Tier 2，仍失败的降级到 Tier 3。

### Tier 1: HTTP 直链（curl / API，可并行）

- **arXiv**: `https://arxiv.org/pdf/{id}.pdf`（并发加 3s delay）
- **Scholar OA 直链**（检索阶段已获取）
- **Unpaywall OA 直链**: `GET https://api.unpaywall.org/v2/{doi}?email={user_email}` → `best_oa_location.url_for_pdf`
- **PMC**: `ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/`（生物医学）

下载：`curl -L -C - --retry 3 -o "{path}" "{url}"`
命名：`作者_短标题_年份.pdf`
校验：文件前 4 字节为 `%PDF` **且 ≥ 50KB**。低于此阈值视为失败（stub 文件、HTML 伪装、登录页 PDF 化均低于 50KB，真实学术 PDF 最小也有数百 KB）

### Tier 2: Headless 解析（需 JS 渲染，不需登录）

- **Sci-Hub**（**≤2021 年才尝试，≥2022 直接跳过**）: 镜像 `sci-hub.se/{doi}` → `.st` → `.ru`，PDF 在 `<iframe>/<embed>` src
- **出版商页面**（轻度反爬）: 解析 DOI 重定向 → 找 PDF 直链
- **Anna's Archive / LibGen**（≤2021，可达性不稳定）

没有 DOI 时先用 CrossRef API 查询：`GET https://api.crossref.org/works?query.title={title}&rows=3`（取结果前必须做标题相似度校验）

### Tier 3: 共享 Chrome（需登录态 / CAPTCHA，串行）

同站点批量处理：解一次 CAPTCHA 后立即顺序处理同站点其他论文，复用会话（约 30 分钟有效）。

- **期刊官网重防护**（ScienceDirect 多层 Cloudflare、Sage 等）
- **CNKI 下载**（需 `cnki_auto_download: true` + 已登录）：**下载前必须告知用户篇数并确认**，会消耗账号额度。详见 `references/cnki-workflow.md`。跳转到付费页则立即停止

### 下载结果标记

完成后更新 Excel 中的下载状态列。

| 状态 | 含义 |
|------|------|
| ✓ 已下载 | PDF 已保存，标注本地文件名 |
| ✗ 需付费 | 附论文页链接 |
| ✗ 需手动 | 验证码等需人工 |
| ✗ 未找到 | 所有渠道均失败 |

---

## Error Escalation

所有无法解决的问题立即用中文告知用户，不静默重试超过一次，不在验证码上循环。
知网遇滑块验证码 → 提示用户在 Chrome 中手动完成；登录失效 → 提示重新登录。
Google Scholar reCAPTCHA 3 次以上 → 停止让用户解，建议换代理节点。
