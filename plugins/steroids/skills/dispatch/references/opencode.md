# OpenCode

**参数和数值都带日期，会过期；调用方式以你当下 `--help` 看到的为准。**
记录它们是因为「问题长什么样」比「用哪个 flag」更耐久——参数改名了，坑还在。

## Provider 与模型（实测于 2026-08）

provider 固定 `ark-coding`（火山 Coding Plan），`opencode models ark-coding` 列全部。

- **主力 `glm-5.3`**：推理和安全能力强，代码审查、安全相关的活优先给它。
- **要长输出换 `deepseek-v4-pro`**：整文件重写、大批量生成这类任务，它 393K 的输出
  上限是唯一扛得住的。输出上限是硬约束，模型再聪明也会被截断。
- 截至 2026-08-19 实测没有 Kimi K3，之后可能上新，以 `opencode models` 为准。

不要凭记忆写模型名，先列一遍。

## 当时可用的调用

```bash
opencode run --pure --auto -m ark-coding/glm-5.3 "$(cat prompt.txt)" < /dev/null
```

| 参数 | 当时的作用 |
|---|---|
| `--auto` | 自动批准权限。help 原文是 "auto-approve permissions that are not explicitly denied (dangerous!)" |
| `--pure` | 不加载外部插件（MCP）。配了远程 MCP 时能避免启动阶段挂死 |
| `--format json` | 输出原始事件流，需要程序化解析时用 |
| `-c` / `--continue` | 续当前目录最近更新的会话；多任务环境不保证是你想要的那一个 |
| `-s` / `--session` | 显式续指定会话 |

## 续问：显式 ID，严格串行

需要可靠继承上下文时，从首轮 JSON 事件取 `sessionID`，后续始终显式传它：

```bash
opencode run --pure -m <provider/model> --format json "<首轮任务>" < /dev/null
opencode run --pure -m <provider/model> --session "$SESSION_ID" --format json "<续问>" < /dev/null
```

`--continue` 只是「最近会话」捷径；同一目录有别的 OpenCode 任务时会续错。更危险的是
**同一 session 没有安全并发**：2026-08-27 实测同时发送 A/B 两问，两进程都退出 0，
但 A 也返回了 B；导出后 A 的 user 消息成为孤儿，两个 assistant 都挂到 B 上。

所以下一轮必须同时满足三个条件才可启动：事件流出现同一 `sessionID` 的
`step_finish`（`reason=stop`）、CLI 进程已经退出、没有另一进程在写这个 session。
中止后先用 `opencode export --sanitize "$SESSION_ID"` 检查最后一条 assistant 是否完整；
残轮不明时新开 session，或明确处理残轮，不能并发重试。纯问答不需要 `--auto`；
是否开启仍按下文的权限与外泄边界判断。

## 权限：`--auto` 是双刃的

不加它时，任何超出当前工作目录的读写都会打印

```
! permission requested: external_directory (/tmp/*); auto-rejecting
```

然后模型**放弃整轮任务**，不会绕开、也不会把已经得到的结论先交出来。撞到过三次：
它想写 `/tmp` 的验证脚本、想读 `~/Library/LaunchAgents/`、想读另一个仓库的配置。

### 只读审查：快照比 `--auto` 更合适

`--auto` 是为「它确实需要动东西」准备的。**只读审查不需要它**，而且用它有两个副作用：
读到的一切都会发给 provider，且没有任何东西拦着它写。

更好的做法是把仓库源码复制一份到临时目录（排除 `node_modules`、构建产物、`.git`、
大体积素材），让它**在副本里跑**。一次解决三件事：

- 全部内容都在 cwd 之内，不触发 `external_directory` 拒绝；
- 物理上碰不到真仓库，"只读"不再靠提示词自觉；
- 它能读到什么由你复制了什么决定——外泄范围是钉死的，不是靠约束它的好奇心。

变更集（diff + 新增文件全文）也一并放进快照，提示词里用相对路径指过去。

**2026-08-26 实测**：同一个审查任务，放在仓库外跑 → 连打两次 `auto-rejecting`，
零字节输出、退出码 0；换成快照后正常读文件并出报告。

## 输入长度墙

同一个模型、同一段提示词结构，只改大小：

| 提示词大小 | 结果 |
|---|---|
| 约 7 KB | 正常，报告完整 |
| 约 10 KB | 正常 |
| 约 49 KB | **只输出一行标题，无内容、无报错、退出码 0** |

而配置里该模型声明的 context 是 1M。所以这堵墙不在模型的上下文上，更可能在
provider 或 CLI 这一层。**不要依赖声明值，按实测拆分。**

## 配额：按时间窗口计，不是按次

`ark-coding`（火山 Coding Plan）有 **5 小时滚动用量配额**。撞上时的形状：

```
Error: You have exceeded the 5-hour usage quota. It will reset at <时间>.
```

这行只出现在 **stderr 末尾**；stdout 里是半截过程旁白，退出码仍是 0。
2026-08-26 实测：一次 84 KB 变更集的代码审查，模型读完文件、镜像测试套件、
跑完测试、验完守卫测试，正要写报告时被掐断——**全部工作白做，产出零字节报告**。

所以：
- 大任务开跑前先估一下这一轮的量，别在窗口快满时启动长审查；
- 提示词里让它**边做边把结论追加到文件**，不要攒到最后一次性输出；
- 一个账号的配额是共享的，同时跑两个实例会更快撞墙。

## 输出里有 ANSI 转义

写进文件后要先清洗才好读：

```bash
sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' out.txt
```
