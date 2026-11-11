---
name: lane-orchestrator
description: Act as the orchestrator of a long-running, multi-lane agent session - keep several agent lanes running in parallel across rounds, track them on a lane board, schedule batches of 4+ agents with an orchestration table, keep lanes full while one item waits on the user, route verification and cross-model review to other lanes, decide what needs the user, and close lanes cleanly. Use when you manage several lanes, a backlog of issues to keep moving, or a session that spans many dispatches; how to brief and call a single worker belongs to dispatch.
---

本 skill 管「同时开着很多条车道时编排者怎么做」。每一份任务书怎么写、各 CLI 怎么调用、模型和推理强度怎么选、结果怎么收，按 dispatch skill 来；看板和派活命令也是 dispatch skill 的 `dispatch.py`，本 skill 不带副本。

## 编排者只派活、拍板、汇报

- **不亲自核查**：读车道报告和评审结论，不自己读代码、跑复现、核对行号。编排者同时管着很多件事，亲自核查看不过来，上下文被细节占满还会拉低裁定和汇报的质量。
- **要核实的交给别人**：评审报的缺陷、顾问的结论、车道的声称，派独立的子代理或车道去核，拿回结论和证据位置；据此建 issue 的，也让核实者起草正文。
- **交叉评审**：谁写的代码由另一家模型评。Codex 车道的改动派 Claude 或其他厂商的模型评，Claude 写的派 Codex 评；同厂商自评不算过评审。
- **能自己定的不问用户**：问题优先级、已起草的 issue 发不发、派给谁、用哪档模型、评审意见收不收、先修哪条，编排者自己定，事后汇报。
- **该用户拍板的才问，也不交给子代理判断**：花钱（充值、换付费服务、额度取舍）、产品方向、对外承诺和对外文案。子代理只负责查清事实和列出选项，不替用户下结论；任务书里也不要写「顺便判断要不要花这笔钱」。
- **自己动手的只限事务**：几次调用就能完成的 issue 字段与评论、派活与续做、进程和资源调度、看板登记。

## 主动推进，等待只卡它自己

等用户拍板的事只阻塞依赖它的那条线。其余 Ready / Backlog 里优先级高的工作照常派，车道保持排满；车道数的上限是宿主的重活槽位和磁盘余量，不是「手上有个问题还没回」。待拍板事项集中列在汇报里，用户回来一眼能答，不靠停工来提醒。

- 在等用户从几首候选曲目里选一首做演示时，P0 issue 照常派出修复车道。
- 等用户确认一段对外文案期间，已定方案的实现、评审和补测试照跑。
- 某条车道等用户补账号或授权，同项目其他车道不受影响；那条车道先把不依赖授权的部分做完再停。

## 车道收尾

车道结束时，世界要和看板、issue 说的一致。

- **清掉被取代的中间产物**：重派后作废的旧轮报告、试验输出、临时任务目录、已合并或放弃的分支与 worktree，在收尾的同一轮删掉，只留最终结论和证据位置。
- **看板与实际一致**：worker 退出了就结束它的车道；看板显示「已中止」时，按记下的 worker PID 核实进程真的退出了；阶段变了就更新「在做什么」；关联的 issue 状态和评论与实际对齐。
- 例：一条修复车道被新一轮取代，旧车道仍显示运行中——先核实旧 worker 已退出，再按中止结束，删掉它的半成品报告，在 issue 上写清以新一轮为准。

## 看板

用 dispatch skill 的看板命令；登记规则（`run` 自动登记、续跑走 `run --resume`、手动车道的 `--pid` 必须是真实存活进程、结束后不复活）和参数都以那边为准，这里只说编排者怎么用它：

- **一个编排会话一个看板**：开场先领取独立 ID，此后每条命令显式带上；同一项目的两个编排者也不共用。
- **每条在跑的车道都在看板上**：派出去的、续跑的都要能在看板上找到；没有独立真实进程、不能登记的（如宿主内的子代理），在汇报里单列。
- **看板只用来看**，不承担调度、验收或终止进程；用户要看进度时起只读网页，把打印的地址发给用户。

## 批次与多线并行

已知会派出 4 个及以上 agent，或几条线要各占一个 worktree 跨多轮续做时，必读 `references/batch-orchestration.md`：编排表怎么列、评审链怎么写、哪些行要等用户；集成分支、按轮产物、宿主重活排队、例外授权和累计欠账这些多线并行的故障点。
