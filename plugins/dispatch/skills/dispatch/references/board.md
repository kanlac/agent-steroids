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

在 **Claude Code 子代理的 shell 工具里，`$PPID` 是长期存活的 `claude` 进程**，因此上例显式传 `--pid "$PPID"`；不要传 `$$`，那是本次短命 shell。其他 CLI 优先显式传 worker PID。`--pid` 省略时默认调用进程 PID（脚本的直接父进程），仅适用于调用进程本身长期存活的场景。绑定宿主 PID 无法发现子代理单独静默中断，编排者仍需显式 `end`；运行中车道超过 10 分钟没有更新时，网页会标出警示，并把最后一次更新之后的时段画成虚线尾巴，可据此识别静默中断。`end` 必须选 `ok` / `failed` / `aborted`，它只记状态、不杀进程。车道结束后不能更新或复活；下一轮重新登记并选择模型、强度和工具。

`run` / `start` / `update` 都可重复传 `--issue URL` 关联网址，只接受完整的 http(s) URL，不限托管平台。`update` 传 issue 时整体替换列表；省略则保留，`--clear-issues` 清空，可单独改 issue 而不传 `--doing`：

```bash
python3 scripts/dispatch.py update --lane "$LANE_ID" --issue https://tracker.example/tickets/163 --issue https://tracker.example/tickets/164
python3 scripts/dispatch.py update --lane "$LANE_ID" --clear-issues
```

车道行内的链接在新标签打开；GitHub / GitLab issue 或 PR 显示 `#163`，同一车道关联多个仓库时显示 `repo#163`，其他网址显示主机名。

## 会话续接

`run` 自动记录 `session_id`：续做时立即使用解析后的会话号；运行中随心跳增量读取本轮事件流，并可读取本轮新写入的会话号文件，收尾再保存一次。拿不到留空，不报错，也不沿用任务目录中无关旧轮次的会话号。`start` / `update` 可用 `--session ID` 手动填写，`update` 可只改会话号：

```bash
python3 scripts/dispatch.py update --lane "$LANE_ID" --session "$SESSION_ID"
```

行内显示前 8 位，悬停显示将复制的完整命令。Claude Code 车道运行中复制 `claude attach <id>`，不加 cd；它接入用 `claude --bg` 启动、仍在后台运行的会话，退出接入后会话继续运行。已结束车道复制 `cd <cwd> && claude --resume <id>`，从保存的记录重开；对仍在跑的会话用 resume 会另起副本。其他已知工具的命令前加 `cd <cwd> && `，工作目录与 ID 按 POSIX shell 规则引用；未知工具只复制完整 ID。复制先尝试 Clipboard API，失败（如 HTTP 机器名页面）后用隐藏 textarea + execCommand；成功短暂提示「已复制」，仍失败则选中显示完整 ID，供手动复制。Windows 用户需在支持 POSIX shell 的终端中粘贴这些命令。

下表于 2026-11-10 逐项查本机 CLI 帮助核实，代码映射固定复用；工具升级后以实际 `--help` 为准。仅生成续接命令，不会自动执行。

| 工具字段 | 复制的续会话命令（不含 cd 前缀） | 核实入口 / 版本 |
|---|---|---|
| `claude` / `claude-agent` / `claude-code` | 运行中：`claude attach <id>`；已结束：`claude --resume <id>` | `claude --help`、`claude attach --help` / 2.1.321 |
| `codex` | `codex resume <id>` | `codex resume --help` / 0.163.0-alpha.10.2 |
| `opencode` | `opencode --session <id>` | `opencode --help` / 1.19.4 |
| `cmd` | `cmd --resume <id>` | `cmd --help` / 1.88.2 |
| `agy` | `agy --conversation <id>` | `agy --help` / 1.4.7 |

## 网页服务

```bash
python3 scripts/dispatch.py board
python3 scripts/dispatch.py board --host 127.0.0.1 --port 18743
python3 scripts/dispatch.py board --allow-host board.example --allow-host alternate.example
```

默认端口 `18743`，默认只绑定 `tailscale ip -4` 返回的地址；取不到就报错并提示 `--host`，不会回退到全网卡。默认绑定时还会从 `tailscale status --json` 的 `Self.DNSName` / `Self.HostName` 读取本机短名和 MagicDNS 全名，去掉末尾点，加入访问白名单；不会允许其他节点名称。终端打印所有允许的 URL，优先打印机器名地址。其他设备可用短名或全名 URL 打开，需具有对应 Tailscale 网络访问权限。读取名称失败会警告并保留 IP 访问，可用 `--allow-host NAME` 手动补充。显式 `--host` 可用于本机验证或自行选择网络。前台手动运行，Ctrl-C 关闭；不安装服务、不改系统设置。

HTTP `Host` 必须匹配绑定地址或白名单中的名称，且带同一个服务端口；缺失、重复、错误端口或未允许的名称返回 400。`--allow-host NAME` 可重复指定，默认绑定和显式 `--host` 均可使用；只传名称，不带协议、路径、端口或通配符，不会改变监听地址。显式 `--host` 时不自动发现 Tailscale 名称。请使用终端打印的 URL；本地代理若无法访问 Tailscale IP，可改用机器名 URL。网页只接受根路径 GET，其他路径 404，写请求不支持；每次请求读状态，数据更新不需要重启。页面把状态作为转义后的 JSON 嵌入，由内联脚本绘制（CSP 只放行该脚本的哈希，不加载任何外部资源），每 5 秒在后台重新拉取根路径并原地重绘，不整页刷新，展开的详情保持不变；单次拉取超过 4 秒即放弃，下一轮照常进行；连续 15 秒拉不到数据会在顶部警示并淡化旧数据。内容：顶部概览（运行中、今天完成 / 失败 / 中止、超时未更新的数量，运行中车道的推理强度分布），下面是全部运行中车道和最近结束的 **20 条**共用一条时间轴的时间线（时间轴从最早的运行中车道或 8 小时内结束的记录起，最长 24 小时；开始早于时间轴的条在左端带 ‹ 标记，整段早于时间轴的记录不画条，只写出起止日期时间），点一行展开工具、模型、目录、PID 等详情。亮色；窄屏下每行改为上下排列，不横向滚动。没有鉴权或 TLS，依靠绑定地址和网络访问控制；不要把它直接暴露到公网。

## 状态与时长

默认状态文件为 `$XDG_STATE_HOME/dispatch/board.json`；未设置 XDG 时为 `~/.local/state/dispatch/board.json`。可用 `DISPATCH_BOARD_STATE` 指定完整文件路径，所有登记进程和网页服务必须使用同一路径。默认 `runs.jsonl` 也在同一个 XDG `dispatch/` 目录；显式 `DISPATCH_ROOT` / `DISPATCH_RUNS` 仍可覆盖任务根目录与账本路径。两份数据各司其职：原有 `status` 仍是运行账本巡检表，并非看板的手动车道清单。

JSON 顶层为 `{"version": 1, "lanes": [...]}`。每条车道包含 `id`、`name`、`doing`、`tool`、`model`、`effort`、`cwd`、`task_dir`、`pid`、`started_at`、`updated_at`、`ended_at`、`status`、`issues`（网址列表）、`session_id`（会话号，未知为空字符串）。旧数据缺少 `issues` / `session_id` 时分别视为空列表 / 空字符串，状态格式仍为 v1。时间用带时区的 ISO 8601；状态为 `running` / `ok` / `failed` / `aborted`。进程锁侧文件加同目录临时文件原子替换，避免并发写坏或丢更新；坏 JSON 会报错，不覆盖。每次写入保留全部运行中和最近 20 条结束记录，不把看板当历史归档。

`run` 每 5 秒更新 `updated_at`，包括等待自动重试期间；手动车道在 `update` 时更新时间。读取时检查本机 PID，消失即按 `updated_at` 显示中止并冻结时长，网页不回写文件。下次命令写入时会持久化这次判定并截断历史。自动车道异常中止的时长通常少算不超过一个心跳间隔；手动车道可能少算更多。PID 复用、僵尸进程及跨机器共享状态无法可靠辨别，状态文件应放在启动任务的本机文件系统；同一任务目录的并发 CLI 执行仍需由编排者隔离。

保留定时心跳：事件流在等待模型、重试或静默工作时不一定有写入；仅用事件文件 mtime 会少算时间，也无法一致表达“宿主仍活着”。当前心跳只维护本轮车道的最后更新时间，手动车道仍靠编排者更新。

自动车道跟踪的是 dispatch 宿主 PID。SIGKILL 宿主时 CLI worker 可能变成孤儿并继续改文件、消耗额度；看板的「已中止」表示派发宿主已停止，**不保证 worker 也已退出**，需要按已记录的 worker PID 核验和清理。
