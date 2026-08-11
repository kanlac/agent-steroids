# ReviewTable —— 治疗确认书

诊断不是修改许可。每条 finding 投影成一行处方，用户逐行决定，保存 JSON 后 Agent 才能治疗。模板：`assets/review-table-template.html`。

## 两种处方

**置信度评改法，不评问题。** 问题可以证据确凿，但删、改、保留哪一种仍取决于用户目标。

- **直接方案 `direct`**：改法机械、无歧义，例如修死链接或改失效命名空间。把完整方案直接写在决定列，标「高把握方案」，默认勾选，允许批注。
- **用户决策 `choice`**：存在偏好、业务目标或结构取舍。把问题和 2–3 个互斥选项直接写在决定列，另给「暂不处理 / 自定义」。默认暂不处理。

不要为方案生成 Diff。大段删除、结构重组无法用短 Diff 准确表达，选项本身才是用户要决定的东西。

## 页面结构

固定三列，保持输入顺序，不把待决项另行置顶：

1. **病灶**（42%）：类型与维度标签、问题、疗效；完整证据用行内 `<details>` 展开，路径可复制。
2. **状态**（14%）：高把握方案 / 需你决定。
3. **决定**（44%）：直接方案的勾选，或互斥选项；每行都有批注。

没有弹窗、没有 Diff、没有单独「建议」列。桌面固定列宽；窄屏改成卡片，长路径换行，不横向挤压。

## 数据契约

每项共有 `id`、`memoryType`、`dimension`、`finding`、`evidence[]`、`kind`、`effect`。直接方案再带 `action`、`solution`、`defaultApply`；决策项带 `question`、`options[]`。每个 option 用稳定 `key`、用户可读 `label` 和 Agent 可执行 `action`。

保存文件固定为 `hippocampus-treatment.json`，落在系统 Downloads 根目录。schema：

```json
{
  "schema": "hippocampus.review-table.v2",
  "source_report": "<报告路径或 id>",
  "projected_score": 84,
  "decisions": [
    {
      "id": "rx-001",
      "kind": "direct",
      "action": "fix-broken-link",
      "solution": "把旧路径改成实际路径",
      "apply": true,
      "note": ""
    },
    {
      "id": "rx-007",
      "kind": "choice",
      "chosen": "A",
      "chosen_label": "统一用 YYYYMMDD-",
      "chosen_action": "修改全局规则为 YYYYMMDD-",
      "apply": true,
      "note": ""
    }
  ]
}
```

`id`、`kind`、`apply`、`note` 保持稳定。`choice` 选择「暂不处理」时 `chosen: "none"`、`apply: false`；选择「自定义」时必须写非空批注。

## 实时疗效分

直接项勾选后计分；决策项选定 A/B/自定义后计分。分数只显示选择带来的预测变化，不暗示未选项必须执行。

## 治疗

用户说「填好了」后读取固定路径，先校验：

- schema 为 `hippocampus.review-table.v2`，source_report 对应本次报告；
- 每个 id 能映射回本次处方，kind 未变；
- direct 的 action/solution 与报告一致；choice 的 chosen 属于原 options，自定义批注非空。

只执行 `apply: true`：direct 按 solution；choice 按 chosen_action；自定义按 note。涉及 skill 重写时遵循 `references/absorb-knowledge.md`。未授权项保持原状，不扩大决定的作用域。

旧报告与确认书是定格病历，治疗后不得回写。要比较疗效，重新体检并生成新时间戳目录。
