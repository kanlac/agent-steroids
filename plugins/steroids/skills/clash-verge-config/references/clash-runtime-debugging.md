# Clash Verge / mihomo 运行态调试

## 调试门槛

修改规则前必须先建立可观测闭环。至少确认：

- 能定位最终运行配置，而不只看到模板或订阅源。
- 能调用当前内核 controller，读取规则、provider、策略组和连接。
- 能运行内核静态配置检查。
- 有可重复触发的测试请求和明确的预期 policy。
- 已保存变更前快照并知道如何回滚。

任一条件不满足时，先修好调试通道，不开始改规则。模板成功渲染、应用提示保存成功、网页能打开，都不能替代运行态证据。

## 证据层级

从低到高收集四层证据：

1. **生成物**：扩展脚本或 Merge 对 mock profile 的输出符合预期。
2. **内核接受**：当前版本 mihomo 对完整最终 YAML 静态检查通过。
3. **运行态存在**：controller 中能看到正确规则顺序、provider 状态和策略组成员。
4. **真实命中**：目标请求的 connection 显示预期 rule、rulePayload、chains 和出口。

前三层只证明“可能生效”，第四层才证明“已经生效”。

## 发现当前内核与 controller

不要硬编码进程路径、端口或应用数据目录。先从当前进程参数发现：

```bash
pgrep -afil 'verge-mihomo|mihomo|clash-verge'
```

关注：

- `-d`：内核工作目录。
- `-f`：真正加载的最终配置。
- `-ext-ctl-unix`：Unix socket controller。
- 最终配置中的 `external-controller` 与 `secret`：TCP controller。

优先使用本机 Unix socket，避免为了调试暴露 TCP 端口。若只能使用 TCP controller，只监听回环或可信局域网，并使用非空 secret。

## 原生工具

优先使用客户端随附的 mihomo 内核做语义校验，避免系统里另一个版本产生假结论：

```bash
"$MIHOMO" -v
"$MIHOMO" -t -d "$CORE_HOME" -f "$FINAL_CONFIG"
```

`-t` 能发现 YAML、provider path、策略引用、重复名称和版本兼容问题，但不会证明目标请求匹配了哪条规则。

## Controller 只读快照

Unix socket 示例：

```bash
SOCKET=/path/to/controller.sock
curl --unix-socket "$SOCKET" -fsS http://localhost/version
curl --unix-socket "$SOCKET" -fsS http://localhost/configs
curl --unix-socket "$SOCKET" -fsS http://localhost/rules
curl --unix-socket "$SOCKET" -fsS http://localhost/providers/rules
curl --unix-socket "$SOCKET" -fsS http://localhost/proxies
curl --unix-socket "$SOCKET" -fsS http://localhost/connections
```

TCP controller 示例：

```bash
BASE=http://127.0.0.1:9097
AUTH="Authorization: Bearer $CONTROLLER_SECRET"
curl -fsS -H "$AUTH" "$BASE/version"
curl -fsS -H "$AUTH" "$BASE/rules"
curl -fsS -H "$AUTH" "$BASE/providers/rules"
curl -fsS -H "$AUTH" "$BASE/proxies"
curl -fsS -H "$AUTH" "$BASE/connections"
```

不要把 secret、订阅 URL、完整节点对象或未脱敏快照写进公开仓库和日志。自动化摘要只保留 provider 名、规则索引、policy、节点逻辑名、时间和计数。

## 规则调试判断

规则从上到下首命中。对每个目标同时回答：

- 预期规则是否存在？
- 它前面是否有更宽的规则提前命中？
- provider 是否已下载且条目数非零？
- policy 名是否对应真实策略组，而不是同名节点或缺失引用？
- 策略组当前选择是否符合失败关闭要求？

`/rules` 中出现目标关键字但 policy 错误，说明规则源或顺序有问题；`/rules` 正确而 `/connections` 命中别处，通常要检查 sniffed host、IP 规则、DNS 解析和旧连接复用。

修改规则后先清除或重新建立目标连接，避免把变更前的长连接当成新结果。不要无差别关闭全部连接，除非用户授权且确有必要。

## 生成、加载与生效不是一回事

Clash Verge 的扩展 Script/Merge 只有在 `enhance()` 重新执行时才进入最终配置。重启应用通常会重新生成；mihomo `PUT /configs` 只重载给定 YAML，不会替 Clash Verge 执行扩展脚本。

因此每次验证都记录三个时间点：

- 模板或扩展脚本更新时间。
- 最终 YAML 生成时间。
- controller 中 provider/连接的运行时间。

只更新前两者而 controller 没变化，不能声称已经应用。

## 真实流量闭环

为每种 policy 选择低副作用、可重复的探针：

- 直连规则：目标 App/站点请求 + connection 中 `chains: [DIRECT]`。
- 固定出口：目标服务请求 + `chains` 指向固定策略组和选中节点，再用出口探针核对公网 IP。
- DNS：检查内部 DNS connection 的 `specialProxy`/chains，而不是用普通 HTTPS 请求替代 DNS 证据。
- 失败关闭：临时使目标 provider 不可用时，请求失败且不出现 `DIRECT` 或普通机场链路。

调试结论至少包含规则索引、匹配类型、rulePayload、policy、chains 和测试时间。截图只能辅助，结构化 controller 数据是主要证据。

## 回归矩阵

规则改动至少覆盖：

- 当前 profile 与另一个结构不同的 profile。
- TUN 开/关中实际使用的模式。
- 域名请求、已有 IP 连接和新建连接。
- provider 正常、缓存命中、更新失败三种状态。
- 目标流量与一个不应受影响的对照流量。

完成后保留脱敏快照和失败样本；关闭临时 controller 暴露、日志 debug 级别和测试代理。
