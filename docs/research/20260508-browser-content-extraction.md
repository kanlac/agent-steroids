# AI Agent 网页内容提取：CDP Native 是最优解

> 调研结论：不需要引入额外依赖（agent-browser、Playwright MCP 等），Chrome DevTools MCP 的 `evaluate_script` 配合精准的 JS 即可高效完成所有浏览器自动化任务。

## 问题的本质

AI agent 操作浏览器有两类需求：
- **导航交互**：找到按钮、输入框，执行操作
- **内容提取**：获取文本、表格数据等

传统方案（完整 A11Y 快照、截图）一次性返回所有信息，在复杂页面上产生 80K+ 字符，浪费大量 token 且经常超出工具返回限制。

## 备选方案概览

| 方案 | 核心思路 | 问题 |
|------|---------|------|
| Playwright MCP `browser_snapshot` | 完整 A11Y 树 | 复杂页面 50K-540K tokens，2-3 页就溢出 |
| agent-browser CLI `snapshot -i` | 只返回交互元素 | 额外依赖，导航省 token 但数据提取仍需 JS |
| Chrome DevTools MCP `take_snapshot` | 完整 A11Y 树 | 同 Playwright，复杂页面不可用 |
| **Chrome DevTools MCP `evaluate_script`** | **精准 JS 提取** | **无额外依赖，最高效** |

## 为什么 CDP Native（evaluate_script）胜出

### 实测 Benchmark

任务：知网检索 3 个子领域 × 40 篇论文 = 120 篇，提取标题、作者、来源、日期、被引、下载。

| 指标 | CDP Native | agent-browser |
|------|-----------|---------------|
| 耗时 | 11m 38s | 1h 45m 22s |
| 总 token 消耗 | 1,886,696 | 6,680,961 |
| 论文数 | 120 | 120 |
| 倍率 | 1x | 3.5x token / 9x 时间 |

两者结果质量相当，但 CDP Native 快 9 倍、省 3.5 倍 token。

### 为什么差距这么大

agent-browser 的 `snapshot -i` 在导航阶段确实省 token（~400 tokens vs 完整快照 80K+），但在数据提取阶段仍需 JS（`eval`）。而 CDP Native 从一开始就用 `evaluate_script`，导航和提取都走 JS——一次调用返回精确结果，不需要中间的快照→解析→操作循环。

agent-browser 的 Bash 调用链（spawn 进程 → 连接 CDP → 执行 → 返回）比 MCP 的直连通道开销更大，120 篇论文的场景下差距被放大。

### 额外依赖不值得

agent-browser 的核心卖点是 `snapshot -i`（交互元素过滤），但：
- `evaluate_script` 用一段 JS 就能实现同样的过滤（见下方示例）
- AI 时代代码实现成本为零——agent 本身就能写出精准的提取 JS
- 引入额外 CLI 依赖增加了安装、版本管理、故障排查的负担
- agent-browser 的渐进式披露（snapshot -i → get text @eN）不如一步到位的 JS 提取高效

## 正确用法：evaluate_script 为主

详细模式和示例见 `skills/cdp-chrome/references/page-interaction.md`。核心原则：

```
navigate_page → 到目标 URL
evaluate_script → JS 提取交互元素摘要（代替 take_snapshot）
fill / click → 交互（或继续用 evaluate_script 操作 DOM）
evaluate_script → 一次性提取结构化数据
```

### 感知页面（代替完整快照）

```javascript
() => {
  const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
    .map(el => ({ tag: el.tagName, type: el.type, placeholder: el.placeholder, id: el.id }));
  const buttons = Array.from(document.querySelectorAll('button, [role="button"]'))
    .map(el => ({ text: el.textContent.trim().slice(0, 50), id: el.id }));
  return { title: document.title, inputs, buttons };
}
```

### 批量数据提取

```javascript
() => {
  const rows = document.querySelectorAll('.result-table-list tr');
  return Array.from(rows).map(row => ({
    title: row.querySelector('.name a')?.textContent.trim(),
    authors: Array.from(row.querySelectorAll('.author a')).map(a => a.textContent.trim()).join('; '),
    source: row.querySelector('.source a')?.textContent.trim(),
    date: row.querySelector('.date')?.textContent.trim()
  })).filter(r => r.title);
}
```

### 何时用 take_snapshot

仅在页面极简（登录页、确认弹窗）或完全未知页面需要先探索结构时使用。

## 结论

Chrome DevTools MCP + `evaluate_script` 是 AI agent 浏览器自动化的最优解。不需要 Playwright MCP（功能重叠且快照过大），不需要 agent-browser（额外依赖，实测更慢更贵）。原生工具 + 精准 JS = 最高效率。
