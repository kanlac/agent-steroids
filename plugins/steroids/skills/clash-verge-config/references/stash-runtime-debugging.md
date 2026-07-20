# Stash 运行态调试

## 调试门槛

Stash 规则、覆写或订阅改动前，必须先让真实设备可调试。最低条件：

- 用户在可信网络主动开启 Remote Controller。
- 已取得设备局域网地址、controller 端口和 API key。
- 调试机能读取版本、规则、策略组和连接。
- 已确定如何更新/禁用覆写并恢复原 profile。
- 已准备目标请求、对照请求和预期 policy。

没有真实 iOS/tvOS Stash 运行态时，只能做制品静态检查，不能宣称移动端已经生效。先准备调试，再改配置。

## 安全边界

Remote Controller 等同于客户端控制面：

- 只在可信局域网或受控隧道开放，不直接暴露公网。
- Stash 3.2+ API 使用 `Authorization: Bearer <secret>`。
- API key 不进入 shell history、公开日志、截图或仓库。
- 测试完成后关闭不再需要的远程访问，恢复日志级别。
- 若 Wi-Fi 有客户端隔离，先解决设备互访，不要为了方便改成公网监听。

Tailscale 与 Stash 都可能占用 Apple Network Extension；不要把“同时开启另一个 VPN”设为唯一调试通道。优先同一可信 LAN。

## 建立只读基线

不同 Stash 版本暴露的 API 表面可能变化。先用只读请求逐个发现，不假设所有 Clash/Mihomo 写接口都可用：

```bash
BASE=http://DEVICE_LAN_IP:CONTROLLER_PORT
AUTH="Authorization: Bearer $STASH_API_KEY"

curl -fsS -H "$AUTH" "$BASE/version"
curl -fsS -H "$AUTH" "$BASE/configs"
curl -fsS -H "$AUTH" "$BASE/rules"
curl -fsS -H "$AUTH" "$BASE/providers/rules"
curl -fsS -H "$AUTH" "$BASE/proxies"
curl -fsS -H "$AUTH" "$BASE/connections"
```

某端点为 `404` 不代表 controller 失效；记录当前版本实际支持的集合，并用 Stash UI 的远程资源、规则、策略组、Connections、HTTP Inspection、DNS Inspection 补足。

基线至少保存脱敏后的：

- Stash 版本与设备时间。
- 当前 profile 名和启用的覆写顺序。
- provider 名、更新时间、条目/节点数和错误状态。
- 前置规则的顺序。
- AI 等固定出口组的成员和当前选择。
- 目标请求变更前的 rule/policy/chain。

## 覆写语义

Stash Override 对字典递归合并、数组前插；多个覆写按 UI 顺序应用。当前版本不能修改数组里的特定元素，所以重点验证合并后的最终数组，而不是只读 `.stoverride` 源文件。

远程规则集可后台更新，不等于远程覆写或基础 profile 已重新合并。需要改变 profile/override 内容时，让用户在 Stash 中执行对应的更新、重新导入或重新启用，然后从运行态确认。不要把 `PATCH /configs` 的 `204` 当作整份配置已替换。

私密覆写优先直接粘贴 URL 或使用本地生成的 `stash://install-override`。不要把含 bearer path/token 的 URL 包进第三方 Web 安装桥。

## 远程资源要分层取证

把 Stash 的远程加载拆成三层，不能用上一层成功替下一层背书：

1. 安装桥只生成跳转。例如 `link.stash.ws` 返回 `stash://install-override?...`，不是内容代理。
2. Override 主文件能导入，只证明该 URL 与 YAML 可用。
3. `rule-providers`、`script-providers`、`proxy-providers` 是独立的嵌套下载；必须在远程资源或 controller 中分别确认状态、更新时间和条目数。

排查域名、CDN 或跳转差异时，用内容完全相同的文件做镜像 A/B：比较最终 URL、HTTP 状态、响应头、字节数和 hash。不要拿结构不同的两份 Override 推断传输层结论。一个只有 `script-providers` 的小文件即使导入成功，也没有验证 rule-provider。

如果小规模规则在真实设备上长期无法可靠完成嵌套下载，可由 adapter 在构建时从权威 policy-free 规则源编译为 Override 的前置 `rules`。这不是复制事实源：生成物不手改，规则变化后重新构建 Override。编译时拒绝 iOS 不支持的 `PROCESS-*`，并把 policy 插在 `no-resolve` 等选项之前。

## 规则与 provider 判断

对目标流量依次确认：

- Override 是否启用且位于预期顺序。
- `rule-providers` 是否下载成功、缓存是否可解析、条目数是否非零。
- 前置 `RULE-SET` 是否位于基础订阅的 `GEOIP`/`MATCH` 之前。
- policy 是否指向真实策略组。
- proxy-provider 是否有节点；空 provider 是否会意外退化为 `DIRECT`。
- 固定出口组是否显式包含失败关闭策略，并由用户选择确定节点。

iOS/tvOS Network Extension 不支持 `PROCESS-NAME` 等进程规则。移动端公共 ruleset 只放客户端共同支持的域名/IP/协议规则；遇到进程规则应由编译器拒绝或分流到桌面专属制品，不能静默忽略。

## 真实设备闭环

静态 YAML 解析和覆写预览只证明结构。最终验收使用真实设备请求：

- 直连集合：目标 App/网页 connection 显示对应 `RULE-SET` 与 `DIRECT`。
- 固定出口集合：Claude/ChatGPT 等请求显示固定策略组与选中节点，并用出口探针确认公网 IP 不漂移。
- profile 独立性：切换至少两个来源和结构不同的 profile，覆写仍保持相同前缀行为。
- DNS：用 DNS Inspection 与实际连接共同判断，不照搬 Mihomo `#PROXY` DNS 语法。
- 失败关闭：provider 无数据或不可更新时，AI 请求失败而不是落到 `DIRECT`/基础 `MATCH`。

旧的 TCP/QUIC 会话可能继续显示变更前链路。测试时重建目标 App 请求或等待旧连接结束，并记录 connection 开始时间；不要只刷新页面。

## 自动化 runner 的边界

可以在调试机写只读 runner：

- 抓取 `/version`、`/rules`、`/providers/rules`、`/proxies`、`/connections`。
- 对 provider 名、规则相对顺序、策略组成员和 selected node 做断言。
- 在用户触发目标 App 请求的时间窗内筛选连接，输出脱敏证据。
- 将同一组 fixture 同时跑向 Mihomo 与 Stash，比较 policy 结果。

runner 不应自动开放 controller、改 profile、安装覆写、切节点或删除连接。会改变设备状态的动作保留为显式用户确认节点。

Stash 没有可替代 iOS 内核的官方无头测试 CLI。通用生成器负责 schema 和能力矩阵，真实 Stash Remote Controller 负责最终语义验收；两者缺一不可。

## 回归矩阵

至少覆盖：

- Wi-Fi 与蜂窝网络。
- 两个不同 profile。
- App 与 Web 两种入口。
- provider 首次下载、缓存命中、更新成功、更新失败。
- 目标流量与不应受影响的对照流量。
- 关闭并重开 Stash 后选择状态、覆写顺序和 provider 缓存仍符合预期。

测试完成后关闭临时 Remote Controller 暴露，保存脱敏结果和精确版本，避免把一次设备成功外推到其它 Stash 版本。
