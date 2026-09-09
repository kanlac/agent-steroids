# OpenCode

## Provider 与模型（实测于 2026-08）

实测环境的 provider 是 `ark-coding`（火山 Coding Plan），`opencode models ark-coding` 列全部。

- **主力 `glm-5.3`**：推理和安全能力强，代码审查、安全相关的活优先给它。
- **要长输出换 `deepseek-v4-pro`**：393K 的输出上限是唯一扛得住整文件重写、大批量生成的。

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

## 权限拒绝

不加 `--auto` 时，任何超出 cwd 的读写都会打印

```
! permission requested: external_directory (/tmp/*); auto-rejecting
```

然后模型**放弃整轮任务**，不绕开、也不把已有结论先交出来。撞到过的：想写 `/tmp` 的验证脚本、
想读 `~/Library/LaunchAgents/`、想读另一个仓库的配置；2026-08-26 把仓库外目录当 cwd 跑审查，
连打两次 `auto-rejecting`，零字节输出、退出码 0。

## 续问：显式 ID，严格串行

从首轮 JSON 事件取 `sessionID`，后续始终显式传它：

```bash
opencode run --pure -m <provider/model> --format json "<首轮任务>" < /dev/null
opencode run --pure -m <provider/model> --session "$SESSION_ID" --format json "<续问>" < /dev/null
```

**同一 session 没有安全并发**：2026-08-27 实测同时发送 A/B 两问，两进程都退出 0，
但 A 也返回了 B；导出后 A 的 user 消息成为孤儿，两个 assistant 都挂到 B 上。

下一轮启动前要同时满足：事件流出现同一 `sessionID` 的 `step_finish`（`reason=stop`）、
CLI 进程已退出、没有另一进程在写这个 session。中止后用 `opencode export --sanitize "$SESSION_ID"`
检查最后一条 assistant 是否完整；残轮不明时新开 session。

## 输入长度墙

同一模型、同一提示词结构，只改大小：

| 提示词大小 | 结果 |
|---|---|
| 约 7 KB | 正常，报告完整 |
| 约 10 KB | 正常 |
| 约 49 KB | **只输出一行标题，无内容、无报错、退出码 0** |

配置里该模型声明的 context 是 1M，所以墙不在模型上下文，在 provider 或 CLI 这一层。

## 配额：5 小时滚动窗口

撞上时 stderr 末尾一行：

```
Error: You have exceeded the 5-hour usage quota. It will reset at <时间>.
```

stdout 里是半截过程旁白，退出码仍是 0。2026-08-26 一次 84 KB 变更集的审查，读完文件、
跑完测试，正要写报告时被掐断，产出零字节。一个账号的配额是共享的，同时跑两个实例会更快撞墙。

## 输出里有 ANSI 转义

写进文件后先清洗：

```bash
sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' out.txt
```
