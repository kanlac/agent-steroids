---
name: clash-verge-config
description: Manage and debug Clash Verge Rev, Mihomo, and Stash client configuration as code, including enhance-pipeline field ownership, scripts, merges and Stash overrides, runtime controllers, profile metadata, routing, DNS and browser leaks, TUN loops, blocked proxy IPs, and cross-profile rule automation. Use when configurations do not apply, rules miss, remote providers or overrides need verification, DNS/WebRTC leaks, profiles show stale metadata, nodes time out, or proxy configuration needs repeatable runtime testing. Server-side proxy/airport build and subscription deployment are out of scope for this client-side skill.
---

## 这个 Skill 解决什么

Clash Verge Rev 是个 Tauri GUI，底层跑 mihomo 内核。它的配置系统有几个**反直觉但有据可查**的行为，不了解会浪费大量时间瞎试。这个 skill 把这些行为的「方向」沉淀下来，让你改配置、做自动化、排查路由时直接走对路，而不是凭印象猜。

核心原则贯穿全篇：**遇到不确定的工具行为，去查一手来源（官方文档 + 源码），不靠猜。** 每条结论都可以、也应该在当前版本上复核。服务端（机场 / 订阅渲染）侧的问题不在本篇范围，属服务端机场运维方法论。

## 心智模型一：字段归属（最重要）

运行时配置由内部函数 `enhance()` 生成，顺序大致是：

```
订阅 profile → 扩展配置(Merge) → 扩展脚本(Script) → ★ Verge 接管保留字段 ★ → 内置脚本 → tun/dns
```

最后那步会**无条件覆盖**一批保留字段——`external-controller`、`secret`、各 `*-port`、`log-level` 等。官方原话：这些字段「由程序自身控制以保证正常功能，无法被成功覆盖」。

这意味着：**保留字段，扩展脚本/扩展配置改不动**，写进去也会被抹掉，不是 bug。要改它们，写进 Clash Verge 自己的 clash 配置文件（应用数据目录里那个带 `#` 头注释的）。而 `proxies`、`proxy-groups`、`rules`、大多数 `dns`/`tun`/`sniffer` 才适合由扩展脚本控制。改了没生效时，先判断是改错层、没触发重新生成，还是规则已生效但被更早规则盖过。

内部细节、保留字段清单、配置文件角色与位置、external controller / external-ui 见 `references/internals.md`。

## 心智模型二：profiles.yaml 与「显示名 / 到期」从哪来

应用数据目录里的 `profiles.yaml` 是 Clash Verge 存 **profile 元数据**的地方：每个远程订阅的 `name`（面板显示名）和 `extra`（`upload/download/total/expire` 流量与到期）。

关键点：**这些值是导入/更新订阅时从服务端响应头解析出来后缓存下来的**——`name` 来自 `Content-Disposition` / `Profile-Title`，`extra` 来自 `Subscription-Userinfo`，**都不是从 URL 推断的**。

由此推出两个实操结论：

- **服务端改了响应头，旧 profile 不会自动变**。显示名或到期不对时，要让客户端重新拉取一次（强制 auto-update 到期 / 重新导入 / 删除重加），缓存才刷新。
- **Clash Verge 不热重载 `profiles.yaml`**。要手改（配置即代码）就先退出 app，再改文件，再重启——退出在前是为了避免退出时把内存里的旧值刷回、覆盖你的修改。改完用「app 重启后实际加载的值」验证，而不是只看你写进文件的值。

## 心智模型三：配置即代码

推荐把全局扩展脚本当成个人规则和自建节点的**叠加层**：订阅提供机场节点，全局脚本幂等注入自建节点、策略组、前置规则和 DNS。换订阅时不重配个人规则，重新生成运行时配置即可。能纯命令行触发重新生成、用 external controller 读写运行时状态，就不依赖 GUI。

## 先准备调试，再改规则

规则或覆写改动前，必须先打通最终运行态读取、保存基线、准备可重复探针和回滚方法。调试通道未就绪时只做静态分析，不修改配置，也不声称已生效。

- Clash Verge / mihomo：读取 `references/clash-runtime-debugging.md`。
- Stash Override / Remote Controller：读取 `references/stash-runtime-debugging.md`。

模板、生成 YAML、内核静态检查、运行态存在、真实连接命中是四层不同证据；最终结论以真实连接的 rule/policy/chains 为准。

## DNS 泄漏与分流规则

「DNS 泄漏」通常不是服务端 Reality 参数问题，而是客户端最终运行时配置没接管 DNS，或 DNS 请求走了 DIRECT/系统解析。处理方向：

- 确认最终运行时配置里确实有 `dns.enable: true`，且没被 Clash Verge 的 DNS 设置或全局脚本覆盖。
- 用 fake-ip / redir-host 时都要明确 `nameserver`、`fallback`/`nameserver-policy` 的出口意图；海外 DoH 用 `https://1.1.1.1/dns-query#PROXY` 这类写法强制经代理解析。
- 代理服务器自身的域名必须有直连解析通道：在 Mihomo 订阅里给 `dns.proxy-server-nameserver` 配国内或系统可达 DNS。普通 `dns.nameserver` 才放带 `#PROXY` 的海外 DoH。否则节点 server 也是域名时，海外 DoH 可能递归成「解析代理服务器需要先连代理」；反过来，如果普通 `nameserver` 直连国内 DoH，DNS leak 检测会显示国内解析器出口。
- 国内域名走国内 DoH 或直连 DNS，国外域名和 AI 服务域名经代理解析，避免本地运营商 DNS 暴露访问意图。
- 验证别只看检测网页结论，要读 mihomo `GET /connections`、日志和最终配置，确认 DNS 连接命中哪条规则、走哪个出站。

临时 Mihomo 专测要隔离端口、controller、工作目录和 TUN，并确认节点入口走物理网卡；但绑定物理网卡后，系统里的 VPN/Tailscale DNS 可能反而不可达，制造 `dns resolve failed` 假故障。出现这种情况先读内核拨号日志，再为节点域名提供物理网络可达的 `proxy-server-nameserver`，或把本次解析结果固定为入口 IP 并保留原 SNI/Host。不要把测试脚手架的 DNS 超时算到节点协议上。

跨客户端订阅不要照搬 DNS 片段。Stash 等客户端的 DNS 请求默认可能直连上游，不按普通代理规则走；mihomo 里可用的 `#PROXY`、海外 DoH、`nameserver-policy` 组合在手机端可能变成「基础 DNS 全超时」，进而让 DIRECT 和节点测速一起失败。遇到 Stash 更新订阅后所有节点超时，优先看订阅是否把桌面 Mihomo 的 `#PROXY/#LEGAL` DNS 原样下发给了 iOS；Stash 常见兜底是独立模板：`redir-host`、直连基础 DNS、入口域名 `hosts`、GEOIP 规则加 `no-resolve`。服务端应按客户端分模板，而不是改 Xray 入站参数。

Stash 的远程 API 更接近运行时控制器，不是 profile 管理器。`PATCH /configs` 只能改 `mode`、`log-level`、端口等少量运行项，不能用 `payload` 替换整份 YAML；`/profiles` 这类 profile 更新接口也不一定存在。验证订阅模板修复时，必须让用户在 Stash 内执行订阅更新或重新导入，再用 `/proxies`、`/rules`、`/connections` 读实际运行态，别把 API 返回 `204` 误判为整份订阅已热加载。

规则同理：从上到下首命中。排查某站没走代理时，找第一条能匹配它的规则，而不是只看最终 IP。

## 浏览器 WebRTC / Secure DNS 旁路：与 Mihomo 分层验收

WebRTC 的 ICE/STUN 候选地址由**浏览器**收集和发包；`dns.ipv6: false` 只控制 Mihomo DNS，运行时顶层 `ipv6: false` 也不是浏览器 WebRTC 的开关。即使 TUN 已接管流量，STUN UDP 仍可能命中 `DIRECT`（例如按目标 IP 的 GEOIP 规则），暴露本地公网 IPv4/IPv6。

出现 WebRTC 泄漏时，先在实际出问题的浏览器 profile 用 `ip.net.coffee/webrtc` 或同类 STUN 检测复现，再同时看 Mihomo 最终配置、路由和 controller 的 UDP connections，确认是未接管还是已接管却走了 `DIRECT`。记录浏览器 binary、user-data-dir 和 `chrome://version` 的 Profile Path；独立 CDP/自动化 profile 的成功只能证明它自己，不能外推到用户日常 Chrome 或无痕窗口。

对 Chromium，优先让浏览器层 fail closed，并明确配置的作用域：

- profile 偏好键 `webrtc.ip_handling_policy=disable_non_proxied_udp` 只保护该 profile，适合局部测试，不是全浏览器证明。
- 企业策略键 `WebRtcIPHandling=disable_non_proxied_udp` 才是跨 profile 的受管方案。macOS 应用 `com.google.Chrome` configuration profile；普通 `defaults write`、随手放置 plist 或只改 DNS 都不能当作受管策略已生效。配置描述文件的安装/替换需要用户在系统设置中批准，不绕过确认。
- 需要让浏览器 DNS 统一由 Mihomo 接管时，再用 `DnsOverHttpsMode=off` 关闭 Chrome 自建 Secure DNS；它解决的是 DNS 路径一致性，不是 WebRTC 开关。

验收时完整退出并重开目标 Chrome，在同一实际 profile 的 `chrome://policy` 核对 policy 名和值、Source=`Platform`、Level=`Mandatory`、Status=`OK`；Scope 可以是当前用户或机器，取决于部署方式。再分别跑 STUN、DNS leak 和普通 HTTPS 出口探针，并用 Mihomo connections/log 交叉验证。三类结果不能互相替代：例如网页主动访问 `1.1.1.1:443` 得到的是普通 HTTPS 出口，不足以证明 Chrome Secure DNS 或 DNS 泄漏。

这会使没有可用 UDP 代理的 WebRTC 失败关闭；需要实时音视频时，再单独验证所选代理链路支持的 UDP/TURN 行为，不能为恢复通话而回退为直连。

## 地理严格的站报「not supported in your country」：先验出口 IP 的 Google 地理，别先怀疑客户端

Gemini 等服务按 **Google 自己的 IP 地理库**判国家——它和 ip-api/ipinfo **经常不一致**。**VPS IP（Bandwagon 等机房段尤甚）常被 Google 标成中国，哪怕物理在美国**。所以 not supported 时**第一步是验出口 IP 在 Google 眼里是哪国**，不是去查客户端泄露（那是罕见的次因，且 ip-api 显示干净并不能排除——要看 Google 的库）。

**检测法**（从该出口或经该节点 `curl`，不是 ip-api）：

```bash
r=$(curl -s -A "Mozilla/5.0" https://gemini.google.com/)
echo "$r" | grep -q '45631641,null,true' && echo 可用 || echo 不可用
echo "$r" | grep -oE ',2,1,200,"[A-Z]{2,3}"'   # 引号里就是 Google 判定的国家码
```

`USA` 且"可用" = 此出口能用；`CHN`/"不可用" = **IP 被 Google 标错国**，改任何客户端/Clash/Xray 配置都救不了——只能换 IP、换节点、或给 Google 报地理纠错。买新节点先跑这条验。

**只有**当出口 IP 的 Google 地理确实是支持国、却仍 not supported 时，才轮到查客户端泄露：浏览器走 IPv6 直连绕过代理，或浏览器 WebRTC 暴露网卡地址。前者看最终运行态 IPv6 与浏览器出口，后者按上面的分层验收处置；不要把关闭 Mihomo DNS IPv6 当作两者的修复。

## 节点突然全超时：先排除 IP 被墙，再排除 TUN 回环

某个一直能用的节点突然延迟测试全 timeout，**先别怀疑订阅格式或节点参数**。两个客户端侧的优先排查：

- **IP 被墙**：从本机网络直接对节点落地 `<server-ip>:<port>` 做 TCP 连接测试（绕开 mihomo）。TUN 不等于无法验证：在 macOS，可把探测 socket 用 `IP_BOUND_IF` 绑定到物理接口（如 `en0`），它不改路由表、不停 TUN，也不会被 fake-ip 路由接走。对节点的 SSH、代理端口和一个预期关闭的高位端口同时测，并用同样绑定方式测一个已知健康节点；目标跨端口超时、健康对照可达、墙外又可达，才可判定为该网络视角的 IP 级封锁。连不上、而换一条已有代理从墙外能连上 = 落地 IP 被封；这时改节点参数、重导订阅都没用，问题在服务端 IP（属服务端机场运维范畴，不在本篇）。
- **TUN 回环**：开 TUN/fake-ip 时，mihomo 的自动分流路由会把「连代理服务器自己那个入口地址」也吞进 TUN，形成回环超时。用 `route-exclude-address` 把本次订阅实际节点 `server` 对应的 IPv4 排除走物理网关：IP 字面量直接排 `<ip>/32`，域名解析当前 A 记录后逐个排 `/32`；macOS 上 `route get <resolved-ip>` 应回到 Wi-Fi 网关而非 `198.18.x.x`。不要只排域名，也不要维护一份旧的入口 IP 清单，尤其是面向别的用户环境时不能假设他们已有本地兜底脚本。
- **代理域名 DNS 递归**：如果 TCP 直连入口成功、`route get` 也走物理网关，但 mihomo 日志出现 DoH 经代理组解析节点 server 并最终 `dns resolve failed`，检查 `dns.proxy-server-nameserver`。节点域名解析不能依赖同一个尚未建立的代理组。

## 远程机器复用本地代理

远程服务器下载海外资源慢时，优先用 SSH reverse tunnel 把远端端口转回本地代理：

```
ssh -f -N -R <remote-port>:127.0.0.1:<local-proxy-port> <remote>
```

判断闭环不要停在「设置了环境变量」：远端用 `curl -x http://127.0.0.1:<remote-port> <url>` 验证目标源可达并测速；本地用 external controller 的 `GET /connections` 或日志确认连接命中预期规则、策略组和出口节点；确定走代理仍慢就切策略组节点重测。对 pip、模型下载、容器拉取等长任务，先确认代理链路和节点质量，再启动大包安装。
