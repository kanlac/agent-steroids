# 编排看板

看板用于随时查看车道，不承担调度、结果验收或终止进程。纯 Python 标准库，无构建、npm 或 pip 依赖。`dispatch.py --help` 与各子命令的 `--help` 是参数入口。

## 自动派活

以下命令均假设当前目录是本 skill 的目录。模型与强度占位值必须换成当前环境实际可用、适合本轮任务的选择。

```bash
python3 scripts/dispatch.py run --name review --agent codex \
  --model "$MODEL" --effort "$EFFORT" --doing "检查修改的边界条件" \
  --cwd "$PWD" --task-dir ./task --prompt-file ./prompt.txt < /dev/null

python3 scripts/dispatch.py run --name review --agent codex \
  --model "$MODEL" --effort "$EFFORT" --doing "复核修复结果" \
  --cwd "$PWD" --task-dir ./task --prompt-file ./followup.txt --resume auto < /dev/null
```

`--agent`、`--model`、`--effort`、`--doing` 每轮必填，空白值同样报错，不从上轮沿用。内部自动重试属于同一轮、同一车道，保留本轮选择。`run` 开始时自动登记，打印的 run ID 就是车道 ID；退出时自动记录正常、失败或中止状态。无结果也属于失败，失败任务返回非零退出码。看板登记、心跳或收尾写入失败只输出警告，不阻止派活，也不覆盖无法识别的新版本状态文件。

没有推理强度旋钮时显式填 `--effort none`：`agy` 只接受 `none`；`cmd` 填 `none` 时不向 CLI 传 effort 参数。`codex` 把所选值原样传给 CLI；能否调节、支持哪些值应按目标工具和模型确认，登记本身不证明配置已生效。

## 手动车道与阶段更新

不经过 `run` 的 Claude 子代理、OpenCode 或其他 CLI，也使用同一份状态。只有 `--name`、`--tool`、`--model`、`--effort`、`--doing` 必填。`--cwd` 默认当前目录，`--task-dir` 可省略、存为 `null`。`--tool` 是自由文本，不限制工具名；`start` 仅输出唯一车道 ID，后续按 ID 操作，同名车道不会覆盖。

```bash
LANE_ID=$(python3 scripts/dispatch.py start --name audit \
  --tool claude-agent --model "$MODEL" --effort "$EFFORT" --doing "检查接口契约" \
  --pid "$PPID")
python3 scripts/dispatch.py update --lane "$LANE_ID" --doing "复核修复与测试"
python3 scripts/dispatch.py end --lane "$LANE_ID" --status ok
```

在 **Claude Code 子代理的 shell 工具里，`$PPID` 是长期存活的 `claude` 进程**，因此上例显式传 `--pid "$PPID"`；不要传 `$$`，那是本次短命 shell。其他 CLI 优先显式传 worker PID。`--pid` 省略时默认调用进程 PID（脚本的直接父进程），仅适用于调用进程本身长期存活的场景。绑定宿主 PID 无法发现子代理单独静默中断，编排者仍需显式 `end`；每张卡片的「最后更新于 X 分钟前」可用于识别长时间未更新的车道。`end` 必须选 `ok` / `failed` / `aborted`，它只记状态、不杀进程。车道结束后不能更新或复活；下一轮重新登记并选择模型、强度和工具。

## 网页服务

```bash
python3 scripts/dispatch.py board
python3 scripts/dispatch.py board --host 127.0.0.1 --port 18743
```

默认端口 `18743`，默认只绑定 `tailscale ip -4` 返回的地址；取不到就报错并提示 `--host`，不会回退到全网卡。其他设备用终端打印的 URL 打开，需具有对应 Tailscale 网络访问权限。显式 `--host` 可用于本机验证或自行选择网络。前台手动运行，Ctrl-C 关闭；不安装服务、不改系统设置。

HTTP `Host` 必须匹配绑定时指定的 `host:port`（包括端口），缺失、重复或不匹配返回 400；请使用终端输出的 URL，未配置的 DNS 别名不接受。网页只接受根路径 GET，其他路径 404，写请求不支持；每 5 秒整页刷新、每次请求读状态，数据更新不需要重启。显示全部运行中车道和最近结束的 **20 条**，亮色、窄屏单列。没有鉴权或 TLS，依靠绑定地址和网络访问控制；不要把它直接暴露到公网。

## 状态与时长

默认状态文件为 `$XDG_STATE_HOME/dispatch/board.json`；未设置 XDG 时为 `~/.local/state/dispatch/board.json`。可用 `DISPATCH_BOARD_STATE` 指定完整文件路径，所有登记进程和网页服务必须使用同一路径。默认 `runs.jsonl` 也在同一个 XDG `dispatch/` 目录；显式 `DISPATCH_ROOT` / `DISPATCH_RUNS` 仍可覆盖任务根目录与账本路径。两份数据各司其职：原有 `status` 仍是运行账本巡检表，并非看板的手动车道清单。

JSON 顶层为 `{"version": 1, "lanes": [...]}`。每条车道包含 `id`、`name`、`doing`、`tool`、`model`、`effort`、`cwd`、`task_dir`、`pid`、`started_at`、`updated_at`、`ended_at`、`status`。时间用带时区的 ISO 8601；状态为 `running` / `ok` / `failed` / `aborted`。进程锁侧文件加同目录临时文件原子替换，避免并发写坏或丢更新；坏 JSON 会报错，不覆盖。每次写入保留全部运行中和最近 20 条结束记录，不把看板当历史归档。

`run` 每 5 秒更新 `updated_at`，包括等待自动重试期间；手动车道在 `update` 时更新时间。读取时检查本机 PID，消失即按 `updated_at` 显示中止并冻结时长，网页不回写文件。下次命令写入时会持久化这次判定并截断历史。自动车道异常中止的时长通常少算不超过一个心跳间隔；手动车道可能少算更多。PID 复用、僵尸进程及跨机器共享状态无法可靠辨别，状态文件应放在启动任务的本机文件系统；同一任务目录的并发 CLI 执行仍需由编排者隔离。

保留定时心跳：事件流在等待模型、重试或静默工作时不一定有写入；仅用事件文件 mtime 会少算时间，也无法一致表达“宿主仍活着”。当前心跳只维护本轮车道的最后更新时间，手动车道仍靠编排者更新。

自动车道跟踪的是 dispatch 宿主 PID。SIGKILL 宿主时 CLI worker 可能变成孤儿并继续改文件、消耗额度；看板的「已中止」表示派发宿主已停止，**不保证 worker 也已退出**，需要按已记录的 worker PID 核验和清理。
