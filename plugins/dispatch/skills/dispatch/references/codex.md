# Codex

## 先发现当前环境

Codex CLI 的模型、参数、工具和权限策略会随版本、账号与宿主环境变化。派发前查看当前 `codex --version`、
`codex exec --help` 和运行时提供的模型列表或工具 schema，不把示例中的模型名、沙箱或审批参数当成通用默认值。

下面只展示稳定的调用形状；先把模型变量替换成当前环境实际可用的值：

```bash
DISPATCH_MODEL_ID="replace-with-an-available-model"

# 探活
codex exec --model "$DISPATCH_MODEL_ID" "只回答两个字：收到" < /dev/null

# 正式任务；仅使用当前版本 --help 确认存在的参数
codex exec --model "$DISPATCH_MODEL_ID" \
  -o result.md --json "$(cat prompt.txt)" < /dev/null > events.jsonl
```

常见参数的语义也要以当前 `--help` 为准：

| 参数 | 用途 |
|---|---|
| `-o result.md` | 把最终回复写入文件，避免只依赖 stdout |
| `--json` | 把机器可读事件流写到 stdout，便于检查停止原因和工具调用 |
| `-c model_reasoning_effort=...` | 在支持该配置键的版本中指定推理强度 |
| `--skip-git-repo-check` | 当前版本要求 git 仓库、而任务目录不是仓库时使用 |

若 CLI 会继续读取 stdin，末尾加 `< /dev/null`，避免非交互任务等待输入。宿主环境可能通过 alias、wrapper、
配置文件或托管策略注入审批与沙箱规则；沿用其正式入口，不为绕开限制而改用底层二进制。

## 权限与网络

文件系统、网络和工具权限由 Codex 版本、启动参数及宿主策略共同决定。不要从某个沙箱名称推断网络一定可用或
不可用；在正式任务前用低成本探活验证所需能力。权限不足时缩小任务或请求正确授权，不让 sub-agent 反复尝试
注定失败的安装、联网或写入操作。

## 收结果

同时保留最终结果文件和事件流。若退出码为 0 但结果为空，检查最后一个事件的停止原因、权限拒绝和配额错误；
不要把某台机器上曾出现的故障形状当成所有环境的固定行为。
