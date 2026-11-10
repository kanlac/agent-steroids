# Command Code

参数和模型名带日期（2026-10-31，v1.88.2），以当下 `cmd --help`、`cmd --list-models` 为准。

## 调用形状

先 `cmd --list-models` 选模型（DeepSeek、Kimi、GLM 等都在列），再用一句话任务探活。正式任务写成「读某个任务书文件并完成」，别把长提示词塞进命令行：

```bash
cmd -p "读 task.md 并完成其中任务" --model "$MODEL" --effort "$EFFORT" \
  --yolo --max-turns 600 --output-format json \
  --no-session --skip-onboarding --no-auto-update < /dev/null > events.jsonl 2> stderr.txt
```

`--effort` 的可选值随模型而定，探活时回显「Reasoning effort set to …」才算生效。后台走工具的后台机制，不加 `&`。

## 权限

`-p` 模式下 shell 命令和写文件必须带 `--yolo`，`--permission-mode accept-edits` 不够（探活得到
「Tool shell_command requires permissions」）。主会话若跑在自动模式，会把 `--yolo` 当成「创建不安全代理」拦掉。

- 解法是**用户自己**在 `~/.claude/settings.json` 的 `autoMode.allow` 里加一条自然语言规则，点名 Command Code 的 `-p` 调用。主会话不能改自己的权限设置，改也会被拦。
- 被拦就停下，把规则文本交给用户；不要换别名、换调用方式绕过去，也不要让别的子代理替你执行。
- 在规则生效前，需要这类委派的任务先用原生子 agent 顶上，并告诉用户换了谁。

## 收结果

同 `SKILL.md`「收结果」：事件流落盘，产物写文件，退出后先看退出码和事件流里的 `error`。

编排看板：使用 `dispatch.py run` 时每轮显式传 `--model`、`--effort`、`--doing`（包括 `--resume`）；直接调用 CLI 或原生子代理时用 `start` / `end` 登记，阶段变化用 `update`。没有强度旋钮时登记 `none`；命令与 PID 约束见 [编排看板](20261110-board.md)。
