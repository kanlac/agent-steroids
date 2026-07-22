# ReviewTable —— 治疗确认书

诊断不是修改的许可。在报告和任何改动之间，隔着一份由用户自己填的确认。形式是 **ReviewTable**：一张可交互的表，Agent 把发现和建议动作铺开，用户逐行审阅、决定，结果存成一份小 JSON，Agent 读回来。它让诊所永远不会不打招呼就改写别人的记忆。

demo 把它做成一份「治疗确认书」——你逐条确认要执行哪些治疗。模板是 `assets/review-table-template.html`。

## 结构

诊断页只给分数；一处缺陷长什么样、证据是什么，全在这一页。报告里处方的每一项对应一行。**列数压到四列**（列太多会挤到字小、路径撑爆），把长内容移出表格：

- **病灶 / finding**——先两枚彩色标签点明「这是哪类问题」：**记忆类型**（预置记忆 / 外部记忆 / 跨两侧的写「预置 ⚔ 外部」）+ **维度**（体量 / 可用性 / 新鲜度 / 矛盾，四色各一）。下面是大白话的问题描述、疗效（+X），以及一个「查看证据」按钮。
- **建议 action**——Agent 打算做什么（删 / 拆 / 移进 skill X / 调和 / 导入）。
- **把握程度 confidence**——高 / 中 / 低。高＝机械，可放心照做。中/低＝需要判断的，视觉上标出来，让视线落在最需要用户看一眼的行上。
- **决定 decision**——唯一属于用户的列：执行 / 跳过，加一栏自由填写。矛盾行的这栏，用来写以哪条为准。

**证据放进弹窗**，不占表格：点「查看证据」弹出，含 `file:line` 与原文引用；矛盾这类有两处证据的，两侧各自成块。每条路径是一枚**可一键复制的 `路径:行号` 芯片**——复制出来能直接粘进编辑器跳到那一行。颜色映射（维度四色、记忆类型）写死在模板，运行时只产数据。

行的默认值取合理动作（高把握默认执行，中低默认待定），但在用户保存并返回之前，什么都不执行。

**数据字段**：每条处方在原有字段外，带上 `memoryType`（`preset` / `external` / `cross`）和 `dimension`（`bloat` / `usability` / `freshness` / `contradiction`）——标签与弹窗都由它们驱动。

## 实时疗效分

预测的健康分随勾选变化：用户开/关一行，就按每项的疗效（+X）重算预测总分并在页面上实时更新。它把确认变成一场看得见的权衡——「这条不勾，我就停在 61」——而不是一张静止的表单。

## 保存 → 读回契约

保存时用下载（Blob）导出一份 Agent 能读的 JSON，**文件名固定为 `hippocampus-treatment.json`**。浏览器 Blob 下载只能落到 Downloads 根目录（进不了报告的时间戳子目录），所以约定它就落在 `~/Downloads/hippocampus-treatment.json`（Windows：`%USERPROFILE%\Downloads\hippocampus-treatment.json`）。用户说「填好了」时，Agent 直接读这个固定路径。schema：

```json
{
  "schema": "hippocampus.review-table.v1",
  "generated_at": "<ISO8601>",
  "source_report": "<诊断报告的路径或 id>",
  "projected_score": 84,
  "decisions": [
    {
      "id": "rx-001",
      "finding": "guard-payload-size 临时方案段已过期",
      "memory_type": "preset",
      "dimension": "freshness",
      "evidence": "agent-steroids/CLAUDE.md:88",
      "action": "delete",
      "confidence": "high",
      "apply": true,
      "note": ""
    },
    {
      "id": "rx-007",
      "finding": "yyMMdd vs YYYYMMDD 命名矛盾",
      "memory_type": "preset",
      "dimension": "contradiction",
      "evidence": "~/.claude/CLAUDE.md ⚔ agent-steroids/CLAUDE.md",
      "action": "reconcile-naming",
      "confidence": "medium",
      "apply": true,
      "note": "统一用 YYYYMMDD"
    }
  ]
}
```

字段名保持稳定（`id`、`action`、`apply`、`note`）——治疗步骤靠它们取值。`id` 必须和报告/表给处方项分配的 id 对上，这样一个决定才能映射回一处具体的改动。

## 页面文案的意图

治疗确认书是对用户说话的，不是旁白。这一页要传达的是：请你把这份清单读一遍，尤其是标着「中把握」「低把握」的那几项——它们最需要你亲自定夺。措辞面向用户、直接、不解说机制。（这一页最显眼的那句引导语，措辞由具体需求定；候选先给用户确认。）

## 治疗

用户返回后，读 `~/Downloads/hippocampus-treatment.json`。**先校验再执行**：`schema` 是否为 `hippocampus.review-table.v1`、`source_report` 是否对得上本次报告（防止串用上一次的旧确认书）、每条 `decisions[].id` 是否能映射回本次处方项。校验过了，只对 `apply: true` 的行执行：

- **高把握 / 机械**——直接执行。
- **中低把握 / 判断**——按 `note` 执行；矛盾就朝用户选的那一侧改。若批了一条「PR 进 skill X」，那次重写走 `references/absorb-knowledge.md` 的方法论（重构而非追加），别把原始笔记钉上去。

然后复述达成的变化（旧分 → 新分），让循环落在一个看得见的改善上。永远不执行用户没勾的行，也不越过一个决定所授权的范围去改。

**已出的报告是一份定格的病历，治疗只改记忆文件、绝不回头改报告。** 用户签完、执行完之后，那份确诊书和治疗确认书（连同当时的分数、证据、处方）原样留在它的时间戳目录里，作为「治疗前」的存档。想看治疗效果，是**再跑一次体检**、生成**新的时间戳目录**做前后对比，而不是覆盖旧报告。这样健康度的历史轨迹一直可回溯。
