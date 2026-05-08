---
name: paper-download
description: |
  Use when the user asks to "download a paper", "find a paper",
  "get PDF for DOI", "下载论文", "找论文", "知网下载",
  or mentions academic paper retrieval needs.
version: 0.5.0
user-invocable: true
allowed-tools: Bash, Read, Write, WebFetch
---

# Paper Download Skill

两阶段学术论文下载：先检索收集元数据，再按成本递增逐级下载。

## 核心原则

1. **检索和下载分离** — 知网/Scholar 用于检索元数据，下载走独立的 Tier 策略
2. **确保论文匹配** — 跨源下载时必须用 DOI 或标题+作者校验，不确定时告知用户
3. **永远不主动付费** — Agent 不点击任何付费下载按钮
4. **逐级升级** — 下载阶段能用 HTTP 直链就不走浏览器导航

## 用户配置

路径：`~/.config/academic-skills/config.json`（首次使用时询问用户后创建）

```json
{
  "cnki_auto_download": false,
  "download_dir": "~/Downloads/papers"
}
```

- `cnki_auto_download`: 允许使用知网机构免费额度自动下载（遇付费页仍停止）
- `download_dir`: PDF 保存目录

## Prerequisites

依赖 `steroids:cdp-chrome` Skill 提供的共享 Chrome 实例（检索和下载均需要）：
1. 读取端口：`cat ~/.config/cdp-chrome/port`
2. 检查是否运行：`curl -s http://127.0.0.1:<port>/json/version`
3. 未运行 → 执行 `~/.config/cdp-chrome/start.sh` 启动
4. 首次使用 → 先 invoke `steroids:cdp-chrome` 完成环境搭建

还需 Playwright MCP（**不要**加 `--isolated`，否则丢失登录态）：
```bash
claude mcp add playwright -s user -- npx @playwright/mcp@latest --cdp-endpoint http://127.0.0.1:<port>
```

---

## 阶段一：检索

目标：拿到结构化论文列表（标题、作者、期刊、年份、DOI、是否 OA）。

### 中文论文 → 知网

详细操作流程见 `references/cnki-workflow.md`。
`browser_navigate` → `https://kns.cnki.net/kns8s/search`，填入关键词，提取结果。

### 英文论文 → Google Scholar

`browser_navigate` → `https://scholar.google.com`，填入关键词/标题。反爬较严，遇验证码提示用户手动完成。

### 元数据补全 → OpenAlex

`GET https://api.openalex.org/works?search={title}&mailto=user@example.com`

返回 DOI、OA 状态（`open_access.is_oa`）、OA 直链（`open_access.oa_url`）、arXiv ID。用于判断走哪条下载路径。

### 结果输出

- ≤10 条 → 直接展示结构化列表
- \>10 条 → 整理为 Excel（标题、作者、期刊、年份、DOI、OA、下载状态）

---

## 阶段二：下载（逐级处理）

### 论文匹配校验

跨源下载必须校验：DOI 精确匹配 > 标题相似度 > 标题+作者+年份。

### Tier 1: HTTP 直接下载

纯 HTTP，多篇并行。来源按顺序尝试：
1. arXiv: `https://arxiv.org/pdf/{id}.pdf`
2. OpenAlex `oa_url`（检索阶段已获取）
3. PMC: `https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/`
4. 期刊官网 URL 模式（Springer: `/content/pdf/{doi}.pdf`，MDPI: `/{path}/pdf`）
5. Sci-Hub（镜像轮询）：`sci-hub.se/{doi}` → `sci-hub.st/{doi}` → `sci-hub.ru/{doi}`
   - PDF 在 `<iframe>` / `<embed>` 的 src 中；2023 后新论文收录低，快速跳过

下载：`curl -L -C - --retry 3 -o "{path}" "{url}"`
命名：`作者_短标题_年份.pdf`，保存到 `download_dir`
校验：文件前 4 字节为 `%PDF`，否则视为失败

### Tier 2: 浏览器导航（无需登录）

串行操作，共享 Chrome session。

**出版商页面：**
1. 解析 DOI 重定向 → 出版商 URL
2. `browser_navigate` → `browser_snapshot` → 找 PDF 按钮 → `browser_click`

**LibGen / Anna's Archive（上述失败时）：**
- LibGen: `https://libgen.is/scimag/?q={doi_or_title}` → 点击镜像链接
- Anna's Archive: `https://annas-archive.org/search?q={query}` → Scientific papers → 下载

必须用 `browser_click` 模拟真实点击，不要用 JS 注入。

### Tier 3: 需要登录的平台

仅用于 Tier 1/2 均失败的论文。

**知网下载**（需 `cnki_auto_download: true` + 已登录 + 有免费额度）：
1. 从知网论文页 `browser_click` PDF 下载按钮
2. 跳转到付费页（`fee_` URL 或"余额不足"文字）→ **立即停止**

### 下载结果回填

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
