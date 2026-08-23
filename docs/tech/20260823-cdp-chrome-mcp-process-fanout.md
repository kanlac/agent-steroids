# cdp-chrome MCP 进程放大问题

> 状态：待决策
> 日期：2026-08-23
> 关联：[CDP Chrome 统一架构](./20260407-cdp-chrome-architecture.md)

## 背景

[20260407 架构文档](./20260407-cdp-chrome-architecture.md)解决了 **Chrome 实例**的复用问题：每个 OS 用户一个 GUI Chrome 进程，所有 skill/agent 通过不同 tab 并行操作，端口和 profile 从 steroids 配置读取。这部分设计是成立的，实测有效。

但它没有约束 **MCP 桥接进程**的数量。`.mcp.json` 里 `cdp-chrome` 是 stdio 类型的 server，意味着**每个 Claude Code 会话、每个 subagent 都会各自 fork 一份**，它们全都只是在给同一个共享 Chrome 当传声筒。

### 实测数据（2026-08-23，一台 16 GB Mac mini，连续开机 28 天）

单个逻辑上的 "cdp-chrome MCP server" 实际展开成四层进程：

```
bash -c (mcp-launcher.sh)
 └─ npx -y chrome-devtools-mcp@latest      ← npm exec 外壳
     └─ node main.js
         └─ chrome-devtools-mcp --browserUrl 127.0.0.1:9224
```

累积结果：

| 进程类型 | 数量 |
|---|---|
| `chrome-devtools-mcp` | 81 |
| `node main.js` | 52 |
| `npm exec chrome-devtools-mcp@latest` | 26 |
| 合计 | **200+** |

这些进程 RSS 都不高，但会被换出到 swap 长期占着。该机器最终 swap 被写到 19.7 GB / 20.5 GB，磁盘可用空间被压到 280 MB。

> 注：当时的主要放大来源是 Agent Teams（`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 下每个带 `name` 的 Agent 调用都会拉起 teammate，而 teammate 会继承全部 MCP 工具）。但即使不用 teammate，"每会话一份 stdio server" 这个基本形态依然成立，只是倍数小一些。

## 约束：上游不支持 HTTP

最直接的想法是把 `cdp-chrome` 从 stdio 改成 HTTP MCP server，这样 N 个会话共用一个远端，本地零 fork。

**但 `chrome-devtools-mcp` 只支持 stdio。** 已核实其完整 `--help` 输出，没有 `--transport`、`--port`、`--http` 之类的参数。它提供的连接选项全部是"如何连到 Chrome"（`--browserUrl`、`--wsEndpoint`、`--autoConnect`），而不是"如何暴露 MCP 自己"。

所以走 HTTP 必须自己在外面包一层网关，不能靠改配置解决。

## 方案 A：去掉 npx（小改动，建议先做）

`mcp-launcher.sh` 末尾当前是：

```bash
exec npx -y chrome-devtools-mcp@latest \
  --browserUrl "http://127.0.0.1:$CDP_PORT" \
  --no-usage-statistics \
  --no-category-performance \
  --no-category-emulation \
  --no-category-network
```

改为固定版本预装、直接 exec 二进制：

```bash
exec "$plugin_root/node_modules/.bin/chrome-devtools-mcp" \
  --browserUrl "http://127.0.0.1:$CDP_PORT" \
  ...
```

**收益：**

1. **砍掉 `npm exec` 整层**——实测占 26 个进程
2. **启动更快**——省掉每次的 registry 解析和版本校验
3. **消除版本静默漂移**——`@latest` 意味着每次启动都可能拉到新版本，行为在无人察觉的情况下改变。这一条和省内存无关，本身就值得改

**代价：** 需要在插件里维护 `node_modules`（或用其他固定版本的分发方式），插件安装流程要相应调整。升级 `chrome-devtools-mcp` 从"自动"变成"显式"——这在稳定性上是好事，但要有人记得升。

## 方案 B：stdio→HTTP 网关（结构性改动，需要进一步验证）

只跑**一个**真正的 `chrome-devtools-mcp` 实例，前面挂一个 stdio↔HTTP 网关，`.mcp.json` 改成：

```json
{
  "mcpServers": {
    "cdp-chrome": { "type": "http", "url": "http://127.0.0.1:<gw-port>/mcp" }
  }
}
```

N 个会话 → 0 个本地 fork。

这和现有架构是**同一个模式**：既然已经在管一个共享 Chrome 守护进程（`start.sh` + `doctor.sh` + 健康检查），再管一个共享 MCP 守护进程不增加新的概念负担，可以复用同一套 steroids 配置、端口校验和 doctor 逻辑。

### 必须先解决的问题

**1. 会话间状态共享。** MCP stdio server 是单客户端模型。一个实例被 N 个会话共享，意味着共享浏览器操作状态——A 会话导航后，B 会话的"当前页"就变了。

上游给了对策，而且写明就是为这个场景设计的：

> `--experimentalPageIdRouting`: expose pageId on page-scoped tools and route requests by page ID (**useful for concurrent agent sessions**)

走方案 B 的话这个参数基本是必选项。但它带 `experimental` 前缀，需要实测验证在多会话并发下是否真的隔离干净。

**2. 网关选型。** 有些 stdio↔HTTP 网关实现是**每个 HTTP 连接再 fork 一个 stdio 子进程**——那样改完等于没改，只是把 fork 从 Claude Code 挪到了网关。选型时必须确认它是真正复用单个 stdio 进程的多路复用实现。

**3. 生命周期与故障恢复。** 现在 MCP server 随会话起停，崩了下次会话自然重来。改成常驻单例后，它崩了会影响所有会话，需要补：
- 健康检查（可以并入现有 `doctor.sh`）
- 崩溃后的自动重启
- 网关挂掉时给出明确错误，而不是让会话卡在连接超时

**4. SKILL.md 约束同步。** 当前文档写的是「禁止自行启动 Chrome 实例，共用共享实例」，这条保住了 Chrome 单例但没约束 MCP 进程数。如果实施方案 B，这里要补一条对应的约束。

## 建议

**先做方案 A**，改动小、收益确定、顺带修掉 `@latest` 的版本漂移隐患。

**方案 B 单独评估**，主要不确定性在 `--experimentalPageIdRouting` 的实际隔离效果和网关选型。在没有验证这两点之前不要动手——如果并发隔离不干净，多会话互相抢浏览器状态会比多几十个进程麻烦得多。

另外，进程数问题的**最大杠杆其实不在这里**：关掉 Agent Teams、给 subagent 定义显式收窄 `mcpServers` 字段，比优化单个 server 的启动方式效果更直接。方案 A/B 是在此基础上的进一步优化。
