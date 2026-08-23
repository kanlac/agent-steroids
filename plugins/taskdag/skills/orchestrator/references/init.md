# 初始化与迁移

## 在新项目启用

1. 复制本 skill 的 `scripts/taskdag.py` 到项目 `scripts/taskdag.py`（vendor 副本，让任何 harness 里的 agent 拿到仓库就能跑，不依赖插件安装）。
2. 建 `docs/tasks/`、`docs/adr/`。
3. 按下方模板写 `docs/tasks/AGENTS.md`，并 `ln -s AGENTS.md docs/tasks/CLAUDE.md`，两个 agent 生态读到同一份。
4. 项目根 CLAUDE.md（或 AGENTS.md）加一行指路，例如：「任务与决策管理见 `docs/tasks/AGENTS.md`，状态用 `scripts/taskdag.py` 操作，不手改」。CLAUDE.md 只写指路，规则不重复。
5. 跑 `python3 scripts/taskdag.py validate` 确认为空仓合法，`new task` / `new adr` 建首批文档，`board` 出看板。

## docs/tasks/AGENTS.md 模板

```markdown
# 任务与决策

本目录（及 ../adr/）由 `scripts/taskdag.py` 管理。schema、状态机、命令的权威说明：
`python3 scripts/taskdag.py help`。

- frontmatter 是状态与关系的唯一事实源；`status` 只能用 `transition` 改，不手改。
- 拆分粒度：一个任务 = 一次可交给单个 agent 的派发；agent 任务标 `model-tier`（high/mid）
  与 `effort`（mid/high/xhigh/max），档位→模型映射见〔按项目指路，如 taskdag skill 的
  dispatch 参考〕。
- `TASK-DAG.html` 是 `board` 命令的生成物（只读视图），改完文档重新生成。
- 改口径、改决策：不改旧 ADR 的实质内容，开新 ADR 并 `supersedes` 互链。
```

按项目情况增删，保持在 20 行以内；调度方法不写这里（属于 skill），项目特有事实（编号历史、归档位置）写这里。

## 项目约定偏差

脚本顶部常量区可改（vendor 副本就是项目配置）：

- `TASK_DIR` / `ADR_DIR`：目录布局。
- `BOARD_FILE`：看板输出路径，可写**绝对路径**把看板发布到仓库外（如一个公网可访问的静态目录）。发布到公网目录时想清楚敏感度——任务正文里的成本、策略、账号安排都会进看板。
- `BOARD_NOTE`：看板头部的当前目标一行（目标不是任务、不进 DAG，用这行保持可见；空串不显示）。
- `NUMBER_FLOOR`：**编号下限**。项目若有历史编号（旧任务清单用过 T01–T41 之类），把下限抬到历史最大号 +1，保证编号永不复用，即使旧号对应的文档没有迁移成 T-* 文件。
- `REQUIRED_TASK_SECTIONS` 等章节名：仅在项目语言不同（如英文仓库）时整体替换。

## 迁移旧任务清单

把一份手维护的任务状态板（表格/清单式 Markdown）转成 DAG：

1. **只迁未完成的、可执行的**：待开始 / 进行中 / 等待中的条目逐条转成 `T-*.md`。已完成条目留在归档文档里，不建文件——除非某个未完成任务 `depends_on` 它（那就建一个 `status: done` 的薄桩，正文按最低要求填）。**目标类条目（结果指标）不迁**：目标放目标文档，用 `BOARD_NOTE` 显示在看板头部，相关任务 `source` 指向目标文档。
2. **编号连续性**：旧清单已有编号的（T01、#12 之类），保持数字不变映射到新格式（T01 → T-001），新任务从历史最大号 +1 开始（设 `NUMBER_FLOOR`）。
3. **忠实转写，不发明**：旧条目的说明进「目标/交付物」，指到的口径文档写进 `source`；旧清单没写验收标准的，按任务性质写出客观证据怎么拿，不虚构范围。
4. **负责人映射**：纯人做的 → `owner: human`；agent 做、人过目/经手的 → `owner: agent` + `manual_acceptance: required`（把人的那一步写成最小动作/通过标准）。
5. **状态映射**：「等待中 ← 某任务」是普通依赖 → `planned` + `depends_on`；「等待中 ← 某外部条件/日期」→ `blocked` + 启动条件写清。
6. **归档旧文档**：顶部加横幅——已归档、被 `docs/tasks/`（T-* 文件 + 看板）取代、日期、理由，并注明「旧编号的解读以本归档为准」；正文保留作历史。全仓扫一遍指向旧文档的引用，改指新位置。
7. 迁移完成：`validate` 全绿 → `board` 生成 → 抽查几个任务的依赖边和 runnable 集合是否符合直觉。
