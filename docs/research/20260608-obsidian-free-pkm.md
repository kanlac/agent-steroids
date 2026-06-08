# 摆脱 Obsidian 桌面端的 Markdown PKM 方案调研

> 创建：2026-06-08

**BLUF**：想要 Obsidian 那套体验（Markdown + YAML frontmatter + `[[wikilink]]` 双链 + 反链）但**不依赖 Obsidian 桌面 App**，正确做法不是找"一个 Obsidian 替代品"，而是**分四层**，每层用一个不依赖 GUI App 的工具：① 格式约定（社区通用标准，谁都不拥有）→ ② 编辑/导航用 **Foam**（VS Code 扩展）→ ③ 结构查询（反链/tag/frontmatter）用 **zk**（Go 单二进制 CLI）→ ④ 语义检索/挂给 AI 用 **qmd**（CLI + 内置 MCP server）。每个 Git 仓库根目录就是一个 vault。这套组合最关键的好处不是"轻"，而是**它能在远程服务器上跑**：CLI 工具直接 SSH 进服务器操作，Foam 走 VS Code Remote-SSH，而 Obsidian 被钉死在桌面 GUI 上、不支持远程连接，远程服务器上的知识库它根本够不着。

## 一、需求拆解

原始需求是「每个项目（Git 仓库）都相当于有一个 Obsidian vault」。核心诉求：

1. 基于 Markdown 的文档管理
2. 包含 Front Matter（YAML）
3. Obsidian 那套标准：`[[wikilink]]` 双链 + 反向链接（backlink）
4. 能**查询**（像 Obsidian CLI 那样方便），但不依赖 Obsidian App

**真正的痛点不是「重」，是「桌面端 + 不能远程」**：Obsidian 是一个必须本地运行的 GUI 桌面应用，**不支持远程连接**——知识库要是放在远程服务器上，Obsidian 就够不着，只能先把文件同步到本地才能看。对「每个项目一个仓库、仓库常驻远程服务器」的工作流，这是硬伤。所以选型的第一性标准是：**工具必须能在没有 GUI 的远程环境里跑**（纯 CLI，或走 VS Code Remote-SSH）。

关键洞察：「查询」其实是**两种不同的需求**，需要两种工具——
- **结构查询**：反链、按 tag / frontmatter 字段过滤、找孤儿笔记 → 需要解析链接关系图
- **语义检索**：按意思 / 关键词把相关文档捞出来 → 全文 + 向量搜索，和链接图无关

把这两者混为一谈，是选型时最容易踩的坑。

## 二、为什么不是「找一个 Obsidian 替代 App」

`[[wikilink]]` 双链 + YAML frontmatter **不是 Obsidian 发明的，也不归它所有**：双链来自更早的 wiki 系统（MediaWiki、TiddlyWiki），YAML frontmatter 来自 Jekyll 等静态站点生成器。Obsidian、Foam、Logseq、Dendron、zk 都是**各自独立采用了同一套社区既成约定**——彼此兼容是自然结果，不是谁抄谁。

所以「格式」这一层是地基，不属于任何工具。只要坚持纯 Markdown + frontmatter + `[[ ]]`，将来想切回 Obsidian、换 Logseq 都无缝，不被锁定。剩下的只是「用什么工具去编辑和查询这堆纯文本」，而这恰好可以**分层、按需叠加**。

## 三、四层方案

| 层 | 作用 | 工具 | 依赖 GUI App? | 远程服务器上怎么用 |
|---|---|---|---|---|
| ① 格式约定 | Markdown + YAML frontmatter + `[[wikilink]]` | 无（社区通用标准） | — | 纯文本，随仓库放哪都行 |
| ② 编辑 / 导航 | 写链接时补全、反链面板、关系图谱 | **Foam**（VS Code 扩展） | ❌ | VS Code **Remote-SSH** 连上去，扩展跑在远端 |
| ③ 结构查询 | 反链、按 tag/frontmatter 查、找孤儿笔记 | **zk**（Go 单二进制 CLI） | ❌ | SSH 进服务器直接跑，纯终端 |
| ④ 语义检索 | 「按意思找文档」、挂给 AI 当后端 | **qmd**（CLI + MCP） | ❌ | SSH 进服务器跑；MCP server 可 `--http` 守护进程暴露 |

② ③ ④ 分别替代了 Obsidian 的「编辑器体验」「Obsidian CLI 的结构查询」「Obsidian 没做好的语义搜索」，且全部脱离桌面 App。**核心区别**：这三者要么是纯 CLI（SSH 进远程服务器直接跑），要么是 VS Code 扩展（走 Remote-SSH 跑在远端）——所以远程服务器上的知识库可以**原地查、原地编辑，不必先同步到本地**；Obsidian 做不到这一点。

### 落地顺序建议

先装 **Foam**（日常编辑 + 反链就够用）→ 需要在终端/脚本里查链接关系再加 **zk** → 想让 AI（如 Claude Code）能语义检索整个笔记库时再加 **qmd**（它的 MCP server 正好挂进来）。不必一次到位。

## 四、候选工具详情

### Foam — 编辑/导航层（VS Code 扩展）

- **形态**：纯 VS Code 扩展（外加几个推荐扩展的「胶水」），无后台进程、无桌面 App。关掉扩展，文件仍是干净的纯 Markdown。
- **vault = 目录**：任意含 `.md` 的文件夹（即 Git 仓库根目录）就是一个 workspace，无需 `.obsidian/` 那种重配置目录。
- **核心功能**：`[[wikilink]]` 自动补全、反向链接面板、关系图谱、`#nested/tag`、frontmatter、笔记模板。
- **语法兼容**：与 Obsidian 同一套 `[[ ]]` + YAML frontmatter，将来切回 Obsidian 无缝。
- **维护状态**：🟢 活跃。
- ⚠️ Foam 与 Dendron 扩展互相冲突，不能同时装。
- 仓库：https://github.com/foambubble/foam

### zk — 结构查询层（CLI）

- **形态**：Go 写的单二进制，**不依赖任何 GUI App**。
- **原生认 Obsidian 那套约定**：`[[wikilink]]`、多种标签语法（`#tag`、`:tag:`）、YAML frontmatter（含 `aliases`）。
- **链接查询是核心能力**：`zk list --link-to <note>` 查反向链接，按 tag / frontmatter 字段过滤、找孤儿笔记等。这是 Obsidian CLI 做不到的（见下）。
- **维护状态**：🟢 活跃（zk-org 社区接手）。
- 仓库：https://github.com/zk-org/zk

### qmd — 语义检索层（CLI + MCP）

> 注：是 Tobi Lütke 的 https://github.com/tobi/qmd ，**不是** Quarto 的 `.qmd` 文件格式。

- **定位**：「a mini cli search engine for your docs」——本地 Markdown 语义/全文搜索引擎。
- **实现**：TypeScript，跑在 Node ≥22 / Bun；索引存本地 SQLite（`~/.cache/qmd/index.sqlite`），FTS5 全文 + sqlite-vec 向量。
- **全本地模型**：`node-llama-cpp` 跑 GGUF——embeddinggemma-300M（向量）+ qwen3-reranker-0.6b（重排）+ 1.7B 查询扩展模型，自动下载到 `~/.cache/qmd/models/`。可用 `QMD_EMBED_MODEL` 换多语言/CJK 模型。
- **三种检索**：`search`（BM25 全文）/ `vsearch`（向量语义）/ `query`（FTS + 向量 + 查询扩展 + RRF 融合 + LLM 重排，推荐）。
- **切块**：~900 token、15% overlap，按标题/代码栅栏智能断点；代码文件（ts/py/go/rs 等）可走 tree-sitter AST 切块。
- **内置 MCP server**：`qmd mcp`（stdio）或 `qmd mcp --http`（localhost 守护进程），暴露 `query` / `get` / `multi_get` / `status` 工具，可直接挂给 Claude Code / Claude Desktop 当检索后端。
- **不做的事**：❌ 不解析 `[[wikilink]]` / backlink，❌ 不处理 frontmatter 链接关系。它只做「按意思/关键词找相关文档」。所以它**补充**而非替代 zk。
- **安装**：`npm install -g @tobilu/qmd`（或 bun）。
- 仓库：https://github.com/tobi/qmd

## 五、被排除的方案

| 方案 | 为什么不选 |
|---|---|
| **Dendron**（VS Code 扩展） | 功能强（尤其层级组织），但 2023 年起进入维护模式、官方基本停更，不宜作长期方案押注；且与 Foam 冲突。 |
| **官方 Obsidian CLI**（`obsidian.md/cli`） | 功能很全（daily、search、读写 vault、headless sync、执行 JS 等），但**必须 Obsidian 桌面 App 在运行才能用**——它本质是给桌面 App 发指令，没解决「桌面端 + 不能远程」的硬伤，直接违背目标。 |
| **Markdown Notes (kortina) / Memo** | 都是 VS Code 双链扩展，可作 Foam 备选，但 frontmatter 支持弱、更新少。 |
| **Quarto（`.qmd`）** | 是「科学写作 + 发布」工具（Markdown + 代码 → PDF/网站/幻灯片），支持 frontmatter 但**完全不做双链/反链/笔记查询**，不在这条赛道上。 |

## 六、一句话结论

> 不要找「一个 Obsidian 替代 App」，而是认准「纯 Markdown + frontmatter + `[[ ]]`」这个不属于任何工具的地基，然后用 **Foam（编辑）+ zk（结构查询）+ qmd（语义检索/AI 后端）** 三个无 GUI 依赖的工具按需叠加。每个 Git 仓库即一个 vault——更重要的是，这套全是 CLI / VS Code Remote 能力，**远程服务器上的知识库可以原地查、原地编辑**，而这正是被钉死在桌面端、不支持远程连接的 Obsidian 永远做不到的。

## 信息源

- Foam：https://github.com/foambubble/foam
- zk：https://github.com/zk-org/zk
- qmd（tobi/qmd）：https://github.com/tobi/qmd
- 官方 Obsidian CLI：https://obsidian.md/cli
