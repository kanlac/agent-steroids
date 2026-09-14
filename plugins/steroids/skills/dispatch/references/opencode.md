# OpenCode

实测于 2026-09，opencode 1.18.30，provider `ark-coding`（火山 Coding Plan）。

## 模型

`opencode models ark-coding --verbose` 看模型名和生效的 `limit`，不凭记忆写。

主力是 `kimi-k3`、`glm-5.3`、`deepseek-v4-pro` 三个，按任务挑，不分高下。挑的时候留意各自的
输出上限（`--verbose` 里的 `limit.output`），它决定单步推理加输出能走多远（见「单步输出上限」）：

- **`kimi-k3`**：配置声明的输出上限 32768，是三个里最紧的。
- **`glm-5.3`**：输出上限 128000。实测习惯把推理集中在一步里，上下文一大单步推理动辄上万 token。
- **`deepseek-v4-pro`**：输出上限 393K。实测推理分散在多步里，单步推理较短。

## 调用

```bash
# 探活
opencode run --pure -m ark-coding/glm-5.3 "只回答两个字：收到" < /dev/null

# 正式任务
opencode run --pure --auto -m ark-coding/glm-5.3 --format json \
  "$(cat prompt.txt)" < /dev/null > events.jsonl 2> stderr.txt
```

| 参数 | 作用 |
|---|---|
| `--pure` | 不加载外部插件（MCP），避免启动阶段挂死 |
| `--auto` | 自动批准未被显式拒绝的权限 |
| `--format json` | 事件流：每次 `tool_use`、每步 `step_finish`（带 `reason` 和 token 数） |
| `-s` / `--session` | 显式续指定会话；`-c` 续的是当前目录最近的会话，多任务时不可靠 |

## 权限拒绝

不加 `--auto` 时，读写 cwd 之外会打印 `permission requested: external_directory (...); auto-rejecting`，
然后模型放弃整轮，零输出、退出码 0。

## 续问必须串行

从事件流取 `sessionID`，续问用 `--session` 显式传。同一会话并发两问，两个进程都会退出 0，
但回答串到同一个问题上。等上一进程退出、事件流出现 `reason=stop` 再发；
残轮不明就用 `opencode export --sanitize <sessionID>` 检查，或新开会话。

## 单步输出上限

每一步（一次模型调用）发出的 `max_tokens` 取模型 `limit.output` 与环境变量
`OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX`（默认 32000）的较小值，**推理 token 也算在内**。
一步推理超限，这一步以 `finish=length` 结束，
没有文本也没有工具调用；循环只在 `tool-calls` 时继续，于是整轮静默结束：退出码 0，stderr 没有错误。

撞不撞取决于**一步想多少**，不是总共想多少。2026-09-14 同一份大文档核对任务：
`deepseek-v4-pro` 总推理 10 万 token，分散在 42 步里，单步最多 2.1 万，一次跑通；
`glm-5.3` 零产出四次：两次在准备动笔的那一步把整份报告放进推理里起草，一步推理到 32000 被截断；
另两次跑到单步 2–2.8 万 token 的长推理中途被停掉。
提示词里要求「先写占位、边写边追加」拦不住。

判别：事件流最后一个 `step_finish` 的 `reason` 是 `length`；没开事件流就 `opencode export`
看最后一条 assistant 的 `finish`。连续几次 Read 同一文件但 `offset` 不同是分页，不是死循环。

配置方式：在 shell 环境里把 `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` 设成很大的数，
等于取消全局上限，再用 `opencode.json` 里各模型的 `limit.output` 分别定。上下文不大的模型别给太大：
没写 `limit.input` 时，自动压缩的阈值是上下文减去这个值，给到和上下文一样大就步步压缩。
`limit.output` 也不能超过服务商的真实上限，否则请求被拒（这种会报错）。

应对：上限放开，留足时间（重推理的单步可达 10 分钟），或换模型。放开上限只免于当场判死，
不保证它按时写文件。早先（2026-08）观察到的「提示词约 49 KB 只输出一行标题」当时没看结束原因，
形状与此一致。

## 配额

5 小时滚动窗口，账号内共享，并行实例更快撞墙。撞上时 stderr 末尾是
`Error: You have exceeded the 5-hour usage quota. It will reset at <时间>.`，
stdout 是半截旁白，退出码 0。**没看到这一行就不是配额**：单步输出截断的产出形状一模一样。
