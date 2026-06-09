# Page Interaction Patterns

`take_screenshot` → `evaluate_script` 是标准流程。`take_snapshot` 仅用于简单页面。

## 工具定位

| 工具 | 用途 | Token 成本 |
|------|------|-----------|
| `take_screenshot` | 看懂页面布局和内容 | ~800–1,600 vision tokens |
| `evaluate_script` | 精准提取数据、操作 DOM | 可控（目标 < 2K tokens） |
| `take_snapshot` | 获取元素 UID 用于 fill/click | 2.5K–135K text tokens |

## 为什么不用 take_snapshot 感知页面

复杂页面（知网、社交媒体、电商）的完整 A11Y 树动辄 80K+ 字符，超出工具返回限制，也会淹没 LLM 上下文。而一张截图只花 ~1K vision tokens，就能让你理解整个页面布局。

## 标准流程

### 1. 看懂页面：`take_screenshot`

对复杂或未知页面，先截图了解布局。这比解析任何文本结构都高效：

```
take_screenshot          → 看到页面长什么样
evaluate_script(JS)      → 基于看到的内容，精准提取/操作
```

对于简单页面（登录页、设置页、确认弹窗），可以直接用 `take_snapshot` 获取 UID 再配合 `fill`/`click`。

### 2. 精准提取：`evaluate_script`

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

### 3. 交互

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

### 4. 批量数据提取

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

### 5. 翻页

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

## 控制返回大小

`evaluate_script` 的优势在于返回大小可控。务必在 JS 端限制输出：

```javascript
// ✅ 好：限制数组长度
() => {
  const items = document.querySelectorAll('.item');
  return Array.from(items).slice(0, 50).map(el => ({
    title: el.querySelector('.title')?.textContent.trim().slice(0, 100),
    link: el.querySelector('a')?.href
  })).filter(r => r.title);
}

// ❌ 坏：返回无限量数据
() => document.body.innerText  // 可能 50K+ 字符
() => document.body.innerHTML  // 可能 500K+ 字符
```

**安全上限参考：**
- 数组结果：`.slice(0, 50-100)` 条目
- 文本字段：`.slice(0, 100-200)` 字符
- 总返回目标：< 8K 字符（~2K tokens）

如果需要提取大量数据，分批处理：

```javascript
// 第 1 页：items 0-49
() => Array.from(document.querySelectorAll('.item')).slice(0, 50).map(...)
// 第 2 页：items 50-99
() => Array.from(document.querySelectorAll('.item')).slice(50, 100).map(...)
```

## 反模式

| 做法 | 问题 |
|------|------|
| 对复杂页面 `take_snapshot` | 80K+ 字符，超限或淹没上下文 |
| 用 snapshot 逐条解析数据 | 每轮都传回完整页面，token 爆炸 |
| 依赖 snapshot 导航交互 | 不如 JS 直接 querySelector 精准 |
| `evaluate_script` 返回 `innerText` / `innerHTML` | 无限量文本，47K+ 字符实测出现过 |
| 不限制数组长度 | 列表页可能有数百条结果 |
