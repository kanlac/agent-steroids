# agy（Google Antigravity CLI）

用法迭代很快，以当下 `agy help`、`agy models` 为准；本文只记思路（2026-11-18，v1.5.10）。

- **什么时候用**：要跨厂商（非 Claude、非 GPT）的写码或评审，或 Codex 额度用完时顶上。额度与 Codex、Claude 各自独立。
- **选模型**：先 `agy models` 看当前套餐给了什么。按用户偏好，最强的 Carbon 系优先，其次 Argon；名字带档位（如 `-high`），档位就是推理强度，所以经 `dispatch.py --agent agy` 时 `--effort` 记 `none`，强度写在模型名里。
- **非交互跑**：`-p` 打印模式，正式任务写成「读某个任务书文件并完成」；需要自动放行工具时显式给权限参数（看 help 里的 mode / skip-permissions），并加 `< /dev/null`。一句话任务先探活。
- **接手别家中断的车道**：它无法续用别的 CLI 的会话。任务书写清现状（HEAD、未提交改动是谁做的、已通过什么、还剩什么），让它先读 diff 再动手。
- **升级**：`agy update`；车道正在跑时先等它结束。
