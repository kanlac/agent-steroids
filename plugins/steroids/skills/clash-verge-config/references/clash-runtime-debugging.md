# Clash Verge / mihomo 运行态调试

## 先保护控制通道

开始前判断当前 agent、远程终端、下载或通知链路是否依赖 Clash Verge。依赖时把现有 app 与 mihomo 视为不可重启基础设施：不退出 app、不停止当前内核、不改占用中的 controller/端口。先保存关键策略组选择；provider 内容用 controller 热刷新，扩展 Script/Merge 只做渲染与静态检查，待独立维护窗口再触发 `enhance()`。

确实必须重启时，先建立不依赖当前 Clash 进程的管理通道，并提前告知用户会有短暂中断。不能把“重启通常能生效”当成当前任务中可无条件执行的动作。

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

## Provider 热刷新与选择保护

远端 provider 内容变化不需要重启 Clash Verge。保存相关策略组的当前选择后，通过当前内核 controller 刷新指定 provider，再确认节点数量、稳定名称和 `alive`；刷新失败时核对旧缓存是否保留，不能自动降级到 `DIRECT`。

```bash
curl --unix-socket "$SOCKET" -fsS -X PUT \
  http://localhost/providers/proxies/<provider>

curl --unix-socket "$SOCKET" -fsS -X PUT \
  -H 'Content-Type: application/json' \
  -d '{"name":"<node>"}' \
  http://localhost/proxies/<group>
```

provider 刷新只更新 provider 数据，不会重新执行 Clash Verge 的 `enhance()`。入口地址变化时，若 Script 还负责 `route-exclude-address` 等静态字段，分别记录“provider 已热更新”和“Script 尚待维护窗口应用”，不要混为同一生效状态。

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

只更新前两者而 controller 没变化，不能声称已经应用。当前代理承载控制会话时，不用重启来弥补证据缺口；保留生成物并明确标记待应用，或在独立 mihomo 中验证完整最终 YAML。

## 独立 Mihomo 验收

临时内核必须使用独立工作目录、mixed-port、controller、缓存和配置文件，关闭 TUN，并绑定预期物理接口；启动和停止都只针对该临时进程。不要复用 Clash Verge 应用目录或用宽泛 `pkill mihomo` 收尾。

controller 请求可用 `--noproxy 127.0.0.1`；经临时代理访问公网目标时不要使用 `--noproxy '*'`，它会连显式 `--proxy` 一起绕过，制造“HTTP 成功但出口不匹配”的本机直连假象。目标探针应清除继承的代理与 NO_PROXY 环境，再显式指定临时 mixed-port：

```bash
env -u http_proxy -u https_proxy -u all_proxy \
    -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u no_proxy -u NO_PROXY \
  curl --proxy http://127.0.0.1:<mixed-port> https://api.ipify.org
```

逐个选择节点并同时验证：controller 当前选择等于目标节点、低副作用 HTTP 探针成功、出口 IP 严格等于该链路预期最终出口。`alive=true` 或延迟成功只能证明探针可达，不能替代真实业务流量和出口核对。

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
- provider 入口变更时，旧入口已从运行态排除、新入口均已加入。运行态可能合并订阅与 Script 的排除项，按“必须包含/必须不存在”做语义比较，不要求与私密 registry 数组逐项完全相等。

完成后保留脱敏快照和失败样本；关闭临时 controller 暴露、日志 debug 级别和测试代理。
