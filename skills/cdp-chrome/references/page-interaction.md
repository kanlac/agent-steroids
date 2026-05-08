# Page Interaction Patterns

`evaluate_script` 是主力工具，`take_snapshot` 是例外。

## 为什么

复杂页面（知网、社交媒体、电商）的完整 A11Y 树动辄 80K+ 字符，超出工具返回限制，也会淹没 LLM 上下文。一段精准的 JS 提取所需数据，比让 LLM 解析海量快照高效得多。

## 标准流程

### 1. 感知页面（代替 take_snapshot）

用 JS 提取页面摘要——只返回你需要的信息：

```javascript
// 提取交互元素摘要
() => {
  const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
    .map(el => ({ tag: el.tagName, type: el.type, placeholder: el.placeholder, id: el.id, name: el.name }));
  const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'))
    .map(el => ({ text: el.textContent.trim().slice(0, 50), id: el.id, className: el.className }));
  return { title: document.title, url: location.href, inputs, buttons };
}
```

### 2. 交互

两种方式：
- **有 uid 时**（从 snapshot 获得）：用 `fill` / `click` 工具
- **无 uid 时**（纯 JS 流）：`evaluate_script` 直接操作 DOM

```javascript
// 填充搜索框并提交
() => {
  const input = document.querySelector('#searchInput, input[type="search"], input[name="q"]');
  if (!input) return 'input not found';
  input.value = '搜索词';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  const btn = document.querySelector('button[type="submit"], .search-btn');
  if (btn) btn.click();
  return 'submitted';
}
```

### 3. 批量数据提取

一次 JS 调用返回结构化数据，不要逐条解析快照：

```javascript
// 示例：提取搜索结果列表
() => {
  const rows = document.querySelectorAll('.result-item, .result-table-list tr');
  return Array.from(rows).map(row => ({
    title: row.querySelector('.title a, .name a')?.textContent.trim(),
    link: row.querySelector('.title a, .name a')?.href,
    meta: row.querySelector('.meta, .source')?.textContent.trim()
  })).filter(r => r.title);
}
```

### 4. 翻页

```javascript
// 点击下一页
() => {
  const next = document.querySelector('.next, a[id*="next"], .pagination .active + * a');
  if (next) { next.click(); return 'clicked next'; }
  return 'no next page';
}
```

## 何时用 take_snapshot

- 页面极简（设置页、登录页、确认弹窗）——元素少，快照小
- 完全未知的页面，需要先了解整体结构再写 JS
- 需要 uid 来配合 `fill` / `click` 工具（但优先考虑纯 JS 流）

## 反模式

| 做法 | 问题 |
|------|------|
| 对复杂页面 `take_snapshot` | 80K+ 字符，超限或淹没上下文 |
| 用 snapshot 逐条解析数据 | 每轮都传回完整页面，token 爆炸 |
| 依赖 snapshot 导航交互 | 不如 JS 直接 querySelector 精准 |
