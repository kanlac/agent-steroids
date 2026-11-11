---
name: dispatch
description: Send a piece of work to a subagent or another model's CLI (Codex, OpenCode, Command Code) and get a usable answer back - brief it like a colleague, pick and verify model and reasoning effort, stay within each CLI's hard limits, grant permissions up front, keep the event stream, and diagnose empty or silent results. Use for a single delegation, a second-opinion review, an independent design, or bulk generation, in any project - including resuming the same worker over several rounds, or working through a backlog one task at a time without coordinating parallel lanes. Also documents its dispatch.py tool (run, status, lane board commands). Coordinating several independent lanes in parallel, or a batch of 4+ agents, belongs to lane-orchestrator.
---

## 像派给同事，不像调函数

- **每次委派都主动选择并显式指定模型和推理强度**，包括原生子 agent、外部 CLI、续跑和评审；不要留空，否则会继承主会话、全局配置或 CLI 默认值。用户已指定的选择优先，否则按任务与验收难度选（模型推荐表与统一强度标尺见 `references/model-effort.md`）。没有推理强度旋钮时显式记 `none`，不能省略或虚填档位。
- **最贵的模型只留给真正难的任务**：长链路调查、反复修不好的根因、高代价设计决策。简单和中等难度的活（明确的小改动、按清单执行、常规评审、调研整理）用常规模型，不因为「保险」就升级到最贵的一档。
- **cwd 就是仓库，给入口和关注点，让它自己读**。不贴源码、不预划只读范围。
- **你知道而它推不出的，写进任务正文**：已修过什么、哪些不能动、怎样算完成、用什么命令验。
  长脚本让它先写进文件再执行，别在工具参数里塞多行 heredoc。
  只有正文会跟着转交和续做走。
- **发现要具体到文件、函数和触发输入**。「建议加异常处理」没法验真假。
- **并行几份给几种侧重**，否则拿回雷同的东西；大审查分批送，一批一个关注面。
- **循环评审优先 resume 同一会话**，它记得哪些已被驳回，不必每轮重读全仓。
- **要同时管多条车道、跨多轮并行，或派出 4 个及以上 agent**，转用 lane-orchestrator skill：编排者准则、编排表和看板怎么用在那里；写每一份任务书仍按本 skill。

## CLI 的硬限制，调用时就要绕开

- **先看 `--help` 和 `models`**。参数和模型名迭代很快，不凭记忆写；长输出先看模型的输出上限，
  那是硬约束。派正式任务前先用一句话任务探活。
- **命令末尾 `< /dev/null`**，否则它等 stdin，零输出挂住。
- **权限一次给够**。被拒后它不绕开、不交已有结论，整轮作废。这是委派不是隔离，别自己加沙箱。
- **单步输出有上限，推理也算在里面**。CLI 给每次模型调用设的上限可能远低于模型本身声明的值，
  重推理的模型上下文一大就一步想穿，这一步没有文本也没有工具调用，整轮静默收工。
  提示词里要求「边写边存」拦不住，要么调高上限，要么换推理轻的模型。
- **长循环宿主自己做**。单次调用有超时，几十个 URL 逐条抓会半途被杀；抓好落盘再交给它分析。
- **配额按时间窗口计**，跑到一半掐断，钱花了产出零。长任务开跑前先估量。
- **后台走工具的后台机制**，命令末尾不加 `&`，也不用 `nohup`、`disown`：绕开它，宿主就收不到完成通知，没人 watch，任务死了或挂了你也不知道。
- **续问用显式会话 ID，等上一进程退出再发**。同一会话并发会串线。并行写代码各给一个 worktree。
- **在任务正文里交代：结束后台进程只按自己记下的 PID**，不按命令行字符串匹配批量 kill。模式一宽就会连它自己的 CLI 进程一起杀掉，整轮中途退出（如 exit 144），改动留在工作区没提交。

## 收结果

- **派出去就要有人等**。启动后确认完成会通知你；不会就另起一个后台命令，循环等进程退出，退出时打印退出码和各输出文件大小。并行派多个时一个命令等全部。
- **后台子代理会被中途打断，而且不通知你**。用户在主会话插话、拒绝某次工具调用，都会让正在跑的后台子代理静默中止，没有完成通知，主会话还以为它在跑（亲历：两个调研子代理分别死在 10:54 和 11:53，一个多小时后才被用户问出来，一条数据都没落盘）。所以：任务书要求每得到一个结果就写进文件，并往进度文件追加一行；启动几分钟后去看产物目录有没有新文件，对不上就读它 transcript 末尾，出现 `Request interrupted` 就是被打断，直接重派，不续等；收到「完成」后核对产物文件真的存在。
- **启动时估一个时长**，到两倍还没动静，读事件流最后几行判断是在干活还是挂住（长提示词当命令行参数、等 stdin、权限被拒都会静默挂住），别干等。
- **让它把结果写进文件**，不靠捕获 stdout。夭折时至少拿回已写完的部分。
- **等进程退出，不等它写的产物文件**。模型死在半路时产物永远不出现，等文件会一直等下去；进程退出后先看退出码和事件流里的 `error`。
- **正式任务开机器可读的事件流并落盘**。每步的结束原因和工具调用序列只在那里，
  事后才有据可查；人读格式的进度多是终端重绘，落盘只剩最后一帧。
- **空白或半截输出、退出码 0，是故障不是「没话说」**。几种原因产出形状一模一样，按证据判，不按形状猜：
  stderr 末尾有 `quota` 行才是配额，换 provider 或等重置，重试无用；`auto-rejecting` 是权限没给够；
  两者都没有，看事件流最后一步的结束原因，`length` 是单步输出被推理吃光。
- **验产物不验转述**。报告会说反提交归属、会声称改了而文件没动；数字要连着产生它的命令看。

## 派活工具 `scripts/dispatch.py`

纯标准库，派 Codex / Command Code（`cmd`）/ Antigravity（`agy`）一条命令搞定：事件流、最终回复、会话号、退出码落进任务目录，模型中途断线或「at capacity」自动续跑，每次开始与结束记一行到 runs 文件，带 token 与费用。`run` 派活（用工具的后台机制跑，等它退出），`status` 打巡检表（`--json` 出机器可读版）。目录与价格表由环境变量 `DISPATCH_ROOT`、`DISPATCH_RUNS` 和同目录 `prices.json` 决定；参数以 `--help` 为准。

`run` 的 `--agent`、`--model`、`--effort`、`--doing` 必填，续跑也重新显式指定。续跑一律走 `dispatch.py run --resume ...`，每轮自动登记新车道，内部重试保留同一车道；不手动补登。首次登记失败就拒绝派活。其他工具用 `start` / `end` 登记车道，`start --pid` 必填且必须是该工作实际存活的本机进程号，不能借用宿主或编排者 PID。没有独立真实 PID 的工作（如宿主内的 Claude 子代理）不登记看板；阶段变化用 `update` 改「在做什么」。

`run` / `start` / `update` / `end` 必须显式传 `--board ID` 或设 `DISPATCH_BOARD`，不要仅按项目共用 ID；单次委派也先用 `new-board` 领一个。`board` 提供根页列表和各 ID 独立的亮色只读网页，默认仅绑定 Tailscale 地址；显示运行中与最近结束的 20 条。看板独立于原巡检账本；状态文件位置、无强度旋钮的 `none` 语义、PID 判活限制与调用示例见 `references/board.md`。何时开新看板、车道怎么排、怎么收尾，属于 lane-orchestrator skill。

## 各 CLI 的细节

参数和数值都带日期，以当下 `--help` 为准。

- `references/model-effort.md` —— 模型推荐表、统一推理强度标尺，以及怎样核对选择真的生效
- `references/board.md` —— `dispatch.py` 的派活与看板命令：自动 / 手动车道、会话续接、网页服务、状态文件
- `references/codex.md` —— 环境发现、通用调用形状、权限与结果诊断
- `references/opencode.md` —— provider / variant 发现、权限、会话、输出截断与配额诊断
- `references/commandcode.md` —— Command Code（`cmd -p`）的调用形状、`--yolo` 与自动模式的关系
