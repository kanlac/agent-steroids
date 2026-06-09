---
name: read-book
description: 翻译 epub 书籍为中英双语对照版，以及阅读和讨论双语书籍。触发场景：(1) 用户要求翻译一本 epub 为双语对照版（"翻译这本书" "做个双语版" "translate this book" "bilingual epub"）；(2) 用户要求阅读或讨论一本 epub 书籍的内容（"读这本书" "讨论这本书" "这本书讲了什么" "summarize this book"）；(3) 用户提到 epub 文件并想了解内容或添加翻译。
---

# 读书：翻译与讨论

## 两种模式

### 模式一：双语翻译

将英文 epub 翻译为中英对照版。每段英文下方插入中文翻译，保留原书排版。

**核心原则：**

- **上下文翻译**：每批段落附带前文作为 context，确保译文自然衔接，消除孤立翻译导致的突兀感
- **样式继承**：翻译段落使用与原文相同的 HTML 标签和 CSS class（标题译为标题大小，正文译为正文大小），不使用统一的翻译样式类
- **标记区分**：所有翻译段落添加 `lang="zh"` 属性，便于后续过滤
- **去重**：只翻译最内层元素——当 `<li>` 内嵌套 `<p>` 时，只翻译 `<p>`，避免重复
- **跳过无需翻译的内容**：署名行（"—Eric Raymond"）、纯人名等本身就是英文的短段落不翻译
- **表格特殊处理**：`<td>` 中的翻译用 `<br/>` + `<span lang="zh">` 追加在同一单元格内，不创建兄弟节点（否则会破坏表格结构）
- **翻译模型**：默认策略是省算力优先  
  - Claude 家族默认走 `sonnet`（不是 Opus）  
  - GPT/CodeX 默认走当前可用的最新 GPT 模型（低算力优先），并使用 `low` effort  
  - 也支持 `--translator codex`，走 `codex exec --skip-git-repo-check --output-last-message`；  
  也支持 `--translator custom --translator-cmd "<cmd>"` 自定义翻译命令。
- **中文排版**：衬线字体（Noto Serif SC / Source Han Serif / Songti SC），翻译段落与下一段英文之间留出足够间距

**使用方法：**

```bash
# 翻译整本书
python3 ${SKILL_PATH}/scripts/translate_epub.py input.epub -o output.epub

# 使用 Codex 进行翻译（headless）
python3 ${SKILL_PATH}/scripts/translate_epub.py input.epub -o output.epub --translator codex

# 使用自定义命令（接入任意 Headless 翻译器）
python3 ${SKILL_PATH}/scripts/translate_epub.py input.epub -o output.epub --translator custom --translator-cmd "python3 my_translator.py"

# 只翻译前 N 个内容文件（适合先试看效果）
python3 ${SKILL_PATH}/scripts/translate_epub.py input.epub -o output.epub --max-files 5
```

环境变量：

```bash
# 覆盖默认翻译后端（claude / codex / custom）
export READ_BOOK_TRANSLATOR=codex

# custom 后端调用命令（可省略 --translator-cmd）
export READ_BOOK_TRANSLATOR_CMD='python3 my_translator.py'

# 可选：给 codex 的模型参数（留空走默认最新 GPT）
export READ_BOOK_TRANSLATOR_MODEL=latest

# 可选：给 GPT/CodeX 的 effort（默认 low）
export READ_BOOK_TRANSLATOR_EFFORT=low
```

脚本需要 `lxml`。首次运行前：

```bash
python3 -c "from lxml import etree; print('ok')"
# 如果缺失，在 venv 中安装：uv venv /tmp/book-venv && source /tmp/book-venv/bin/activate && uv pip install lxml
```

### 经验沉淀（避免重复问题）

#### Negative few-shot（禁止行为）
- 遇到以下输出时认为本次翻译失败，必须重跑：
  - `我会先...按这个格式返回...`
  - `以下是第X段的翻译：`
  - `I will translate...` / `I can't translate image...`
  - 任何说明模型流程、输出格式、进度或自我评价的句子
- 只允许输出 `"[N] 中文"` 行；若有任一行不是译文或不包含中文编号段落，立即判定污染。

#### 自动补齐闭环（目标行为）
- 全量执行默认开启：每个批次先做翻译 → 自动检测缺漏/污染 → 自动补齐（先单段重跑，默认 2 轮）→ 最终写入 EPUB。
- 默认脚本会自动给出 `已翻/应翻/未补齐` 统计，不需要手工中断和二次分发命令。

#### 验收规则（最小闭环）
- 先跑 `--max-files 1~3`，只看两个信号：是否出现 `lang="zh"` 译段，是否有说明性文本夹杂。
- 通过后再继续全量；不通过则回退到更小批次并单段补齐，不直接重放全量。
- 全量后仍有系统说明文本或大规模缺段，改用 `--translator custom` 并重跑新文件名。

### 模式二：阅读与讨论

当用户想讨论一本书的内容时：

**读双语 epub：** 带 `lang="zh"` 属性的段落是机器翻译，仅供用户阅读参考。Agent 分析和讨论时只读原文段落，忽略 `lang="zh"` 的翻译段落，以原文为准。

**读普通 epub：** epub 本质是 zip 包，解压后在 `OEBPS/` 目录下找 `.xhtml` 文件，按 `content.opf` 中的 `<spine>` 顺序阅读。

**讨论方法：**

- 先通读目录（TOC），建立全书结构认知
- 按用户指定的章节或主题深入阅读
- 讨论时引用原文关键段落，给出分析和观点
- 将书中观点与更广泛的知识联系起来，提供跨领域洞察
