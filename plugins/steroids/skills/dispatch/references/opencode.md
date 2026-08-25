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
| `-c` / `--session` | 续上一轮会话 |

## 权限：`--auto` 是双刃的

不加它时，任何超出当前工作目录的读写都会打印

```
! permission requested: external_directory (/tmp/*); auto-rejecting
```

然后模型**放弃整轮任务**，不会绕开、也不会把已经得到的结论先交出来。撞到过三次：
它想写 `/tmp` 的验证脚本、想读 `~/Library/LaunchAgents/`、想读另一个仓库的配置。

加上它之后另一面要记住：**它读到的一切都会发给 provider**，而且它很会顺着代码
往外摸——审查取数模块时摸进真实数据目录、审查部署脚本时摸到凭据文件，都发生过。
所以开了 `--auto` 就更要在提示词里划定范围，见 SKILL.md 的「派活之前」。

## 输入长度墙

同一个模型、同一段提示词结构，只改大小：

| 提示词大小 | 结果 |
|---|---|
| 约 7 KB | 正常，报告完整 |
| 约 10 KB | 正常 |
| 约 49 KB | **只输出一行标题，无内容、无报错、退出码 0** |

而配置里该模型声明的 context 是 1M。所以这堵墙不在模型的上下文上，更可能在
provider 或 CLI 这一层。**不要依赖声明值，按实测拆分。**

## 输出里有 ANSI 转义

写进文件后要先清洗才好读：

```bash
sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' out.txt
```
