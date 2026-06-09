# AI Agent 浏览器自动化方案调研

> 更新于 2026-06-09。初版 2026-05-08 仅对比了 CDP Native 与 agent-browser；本次新增 bb-browser 对比、截图感知策略、工具定义税分析。

## 问题的本质

AI agent 操作浏览器有两类需求：
- **导航交互**：找到按钮、输入框，执行操作
- **内容提取**：获取文本、表格数据等

传统方案（完整 A11Y 快照）一次性返回所有信息，在复杂页面上产生 80K+ 字符，浪费大量 token 且经常超出工具返回限制。

## 方案概览

| 方案 | 核心思路 | Token 效率 | 额外依赖 |
|------|---------|-----------|---------|
| Playwright MCP `browser_snapshot` | 完整 A11Y 树 | ❌ 50K-540K tokens/次 | playwright |
| agent-browser `snapshot -i` | 交互元素过滤 | ⚠️ 导航省但提取仍需 JS | agent-browser CLI |
| Chrome DevTools MCP `take_snapshot` | 完整 A11Y 树 | ❌ 同 Playwright | 无 |
| **bb-browser site adapter** | **调站点内部 API** | **✅ ~200 tokens/次** | **bb-browser daemon** |
| **CDP Native screenshot + evaluate_script** | **截图感知 + 精准 JS** | **✅ ~2K tokens/次** | **无** |

## CDP Native vs agent-browser：实测 Benchmark

任务：知网检索 3 个子领域 × 40 篇论文 = 120 篇，提取标题、作者、来源、日期、被引、下载。

| 指标 | CDP Native | agent-browser |
|------|-----------|---------------|
| 耗时 | 11m 38s | 1h 45m 22s |
| 总 token 消耗 | 1,886,696 | 6,680,961 |
| 论文数 | 120 | 120 |
| 倍率 | 1x | 3.5x token / 9x 时间 |

两者结果质量相当，但 CDP Native 快 9 倍、省 3.5 倍 token。

差距原因：agent-browser 的 `snapshot -i` 在导航阶段省 token，但数据提取仍需 JS。而 CDP Native 从头就用 `evaluate_script`，不需要快照→解析→操作的中间环节。agent-browser 的 Bash 调用链（spawn 进程 → 连接 CDP → 执行 → 返回）开销也更大。

## bb-browser 对比分析

bb-browser（[epiral/bb-browser](https://github.com/epiral/bb-browser)）是一个 CLI + MCP server，核心理念是"Your Browser is the API"。同样连接用户已登录的 Chrome，通过 CDP 操作。

### bb-browser 的独特优势：Site Adapter

bb-browser 的最大差异化不是工具层面，而是使用范式：

```bash
# bb-browser：预建 adapter 直接调站点内部 API，绕过 DOM
bb-browser site twitter/search "AI agents"      → 结构化 JSON
bb-browser site xueqiu/hot-stock 10             → 结构化 JSON
bb-browser site github/repo-issues "org/repo"   → 结构化 JSON

# CDP Native：LLM 现写 JS
take_screenshot → 看页面
evaluate_script → LLM 编写提取逻辑
```

adapter 直接调站点的内部 JSON API（如 Twitter 的 GraphQL endpoint），用浏览器 cookie 鉴权，**完全绕过 DOM**。社区仓库 `epiral/bb-sites` 已有 100+ 个 adapter。配合 `--jq` 内联过滤，在数据到达 LLM 之前就裁剪输出。

### 对比总结

| 维度 | CDP Native (我们) | bb-browser |
|------|-------------------|------------|
| 底层能力 | 完整 CDP 访问 | 完整 CDP 访问 |
| 有 adapter 的站点 | ~2K tokens/次 | ~200 tokens/次（10x 优势） |
| 无 adapter 的站点 | ~2K tokens/次 | 类似 |
| 灵活性 | 任何站点立即可用 | 需要预建 adapter |
| 部署复杂度 | MCP 直连 | 额外 daemon 进程 |
| 额外依赖 | 无 | bb-browser + bb-sites |

### 评估结论

bb-browser 的 site adapter 对高频使用的固定站点有显著优势（10x token 节省），但：
- 需要额外安装、维护 daemon 进程
- 无 adapter 的站点退化为类似的通用方案
- adapter 依赖站点内部 API，站点更新可能 break
- 我们可以在 `references/` 下积累类似的 JS snippets 达到部分效果，而不引入额外依赖

**不采纳 bb-browser 作为替代方案，但借鉴其"减法思维"优化 CDP Native 方案。**

## 工具定义税：隐性成本分析

2026-06 分析本机 256 个含 CDP 调用的 Claude 会话，发现 17% 的 token 用量来自 cdp-chrome，但**最大头不是工具返回值，而是工具定义的 input token 开销**。

### 问题

`chrome-devtools-mcp@latest` 默认注册 30 个工具，每个工具定义约 ~300 tokens。每次 API 调用（每轮对话）都要重发所有定义：

- 30 个工具 × ~300 tokens = ~9,000 input tokens/turn
- 实际只用了 9 个工具，21 个从未调用
- 浪费的定义税：~6,300 tokens/turn

### 优化

通过 `--no-category-performance --no-category-emulation --no-category-network` 禁用 3 个从未使用的工具类别，减少约 7 个工具定义，每轮省 ~2,100 input tokens。

剩余未使用的工具（`drag`、`fill_form`、`handle_dialog` 等）暂时保留——如果后续确认不需要，可进一步使用 `--slim`（仅保留 3 个工具：navigate + evaluate_script + screenshot）。

## 正确用法：截图感知 + evaluate_script 为主

### 标准流程

```
navigate_page      → 到目标 URL
take_screenshot    → 看懂页面布局（~1K vision tokens，远低于 take_snapshot 的 2.5K-135K text tokens）
evaluate_script    → 基于视觉理解，精准 JS 提取/操作
evaluate_script    → 一次性提取结构化数据
```

### 工具选择

| 目的 | 工具 | Token 成本 |
|------|------|-----------|
| 看懂页面布局 | `take_screenshot` | ~800–1,600 vision tokens |
| 精准提取/操作 | `evaluate_script` | 可控（目标 < 2K tokens） |
| 获取元素 UID（简单页面） | `take_snapshot` | 2.5K–135K text tokens |

### 关键原则

1. **复杂/未知页面先截图**——`take_screenshot` 比 `take_snapshot` 便宜 10-100 倍，且提供更好的空间理解
2. **take_snapshot 仅限简单页面**——登录页、设置页、确认弹窗（A11Y 树 < 5K chars）
3. **evaluate_script 返回要限制大小**——数组 `.slice(0, 50-100)`，文本 `.slice(0, 8000)`，总返回目标 < 8K chars
4. **不要返回 innerText/innerHTML**——实测出现过 47K chars 的单次返回

详细模式和示例见 `plugins/chrome/skills/cdp-chrome/references/page-interaction.md`。

### 何时用 take_snapshot

仅在页面极简（登录页、确认弹窗）且需要元素 UID 配合 `fill`/`click` 时使用。

## 结论

Chrome DevTools MCP + `take_screenshot` + `evaluate_script` 是 AI agent 浏览器自动化的最优通用解。不需要 Playwright MCP（快照过大），不需要 agent-browser（额外依赖，实测更慢更贵），不需要 bb-browser（额外 daemon，仅在有 adapter 的站点有优势）。

优化后的工具链：禁用不必要的工具类别 + 截图优先感知 + 精准 JS 提取 = 最高效率 + 零额外依赖。
