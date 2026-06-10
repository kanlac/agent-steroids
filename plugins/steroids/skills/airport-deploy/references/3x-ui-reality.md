# 3X-UI / VLESS Reality 运维参考

> 面向自建自用代理栈。不要把真实 IP、域名、UUID、subId、面板账号、API token 或证书私钥写进公开文档。

## 部署基线

- SSH 改非默认端口，启用公钥登录，禁用密码登录。
- 监听地址 / 防火墙收口：对公网只暴露 Reality 端口和对外订阅端口；面板端口、以及由自建服务/反代承接时的 3X-UI 原生订阅端口，都优先只监听 `127.0.0.1`（订阅监听见「订阅服务」）。
- 开启 BBR 可以作为基线优化，但它不能解决所有跨境拥塞。
- 3X-UI 安装后立刻改用户名、强密码、面板端口和随机 path。
- 面板后台建议用 SSH 隧道访问：`ssh -L <local-port>:127.0.0.1:<panel-port> <server>`。

## Reality 入站

一台机器通常只需要一个 VLESS Reality + Vision 入站：

- `port`: 常用 `443`。
- `transmission`: `tcp`。
- `security`: `reality`。
- `flow`: `xtls-rprx-vision`。
- `dest` / `serverNames`: 选择真实、稳定、支持 TLS 1.3 的大站，SNI 与 dest 域名保持一致。
- `fingerprint`: 常用 `chrome`。
- Reality x25519 key pair 和 short-id 属于入站级参数，所有 client 共用。

每个用户单独维护：

- `email` / remark：可读用户标识。
- `id`: UUID，每人唯一。
- `subId`: 订阅链接标识，每人唯一；疑似泄露时只换它。
- `expiryTime`: 到期时间；续期只改这个字段。
- `enable`: 停用用户时优先关 enable 或删除该 client。

3X-UI 的持久化模型会随版本演进，遇到「面板有用户但生成的 Xray config 里 `clients` 为空」之类问题，先确认当前版本源码和数据库关系，而不是直接改生成文件。以 3X-UI v3.2.x 为例，client 与 inbound 的关系由 `client_inbounds` 表维护，生成 Xray config 时再从该表关联 client；只改 `inbounds.settings` 可能会被重生成覆盖。修复顺序应是停服务、备份数据库、补齐权威关系表、重启后验证生成 config 和实际端口。

## 订阅服务

3X-UI 原生订阅适合输出节点信息，但不一定适合所有 Clash/Mihomo 客户端直接作为远程 YAML 导入。遇到 `remote file is invalid YAML` 时，先看响应体是不是 base64 或 `vless://` 裸节点列表；如果是，就需要转换器或模板生成完整 YAML。

自建 YAML 订阅服务时建议：

- 从 3X-UI 数据库或受控用户清单读取 UUID/subId/到期状态，不手写散落配置。
- URL 可继续使用短 subId，显示名通过响应头控制。
- 设置 `Profile-Title: <user>`。
- 设置 `Content-Disposition: attachment; filename=<user>`，避免加引号和 `.yaml` 后缀导致某些客户端显示转义字符。
- YAML 内集中下发 `proxy-groups`、`rules` 和 `dns`，或明确告知用户必须使用全局 Merge/Script。
- 在响应头里随节点下发 `Subscription-Userinfo: upload=0; download=0; total=<字节>; expire=<unix 秒>`，客户端会在 profile 卡片显示到期日期和剩余天数。`expire` 由 `expiryTime`(毫秒)/1000 得到；不限量（`totalGB=0`）时省略 `total`，避免客户端算出 0/0 流量环。到期信息走响应头，别塞进节点名——节点名要稳定，否则客户端按名字保存的"选中节点"会在改名后丢。

**收口原生订阅监听**：3X-UI 订阅服务默认监听所有网卡（`subListen` 为空 = 等价 `0.0.0.0`），且 `webListen` 收了不代表订阅收了——两者是独立设置。若对外由自建 HTTPS 服务/反代承接订阅，应把原生订阅设为 `subListen=127.0.0.1`，否则原生订阅端口（含 `subClashEnable` 打开的原生 `/clash/` 旁路）会裸奔公网，平白多一条暴露面。改完用 `ss -ltn` 确认绑定变成 `127.0.0.1:<sub-port>`，再从外部确认该端口连接被拒。

**临时明文 HTTP 必须有退出条件**：为了迁移旧客户端可以短期开一个 legacy HTTP 订阅端口，但它不是长期入口。完成迁移后关掉服务开关、重启订阅服务，验收时看两件事：HTTPS 订阅端口仍公网可达；明文 HTTP 端口不再绑定公网地址（若 3X-UI 内部端口还在，只能是 `127.0.0.1:<port>`）。

**改 3X-UI 设置走数据库时先停服务**：设置存在 `x-ui.db` 的 `settings` 表（`key/value`）。x-ui 运行时占着 SQLite 写锁，直接 `sqlite3` 写会报 `database is locked` 并静默失败。正确顺序：`systemctl stop x-ui` → 备份 + 写库 → `systemctl start x-ui` → `ss` 验证。注意这会重启 Xray、短暂中断数据面（443）。

## 域名与证书

Reality 不依赖自有域名和证书。自有域名主要用于：

- 面板 HTTPS。
- 订阅 HTTPS。
- 换 VPS IP 后让用户链接不变。

Cloudflare 只做解析时必须 DNS only / 灰云。橙云会让流量经过 Cloudflare，不适合 Reality 直连，也可能违反免费版代理流量限制。

ACME 失败时按顺序排查：

- 注册商域名验证是否完成。
- Cloudflare zone 是否 active。
- NS 是否已经切到 Cloudflare。
- `dig` 是否能解析到 VPS IP。
- A 记录是否灰云。
- VPS 防火墙是否放行 HTTP-01/TLS-ALPN 所需端口，或 3X-UI 当前 ACME 模式需要的端口。

HTTP 订阅可以临时测试，但不适合长期分发，因为 subId、UUID 或节点参数可能被链路旁路观察到。

## DNS 与规则

订阅里如果只下发节点，不下发 DNS/规则，就不能保证用户侧没有 DNS 泄漏。集中维护可以选择两种模式：

- 服务端 YAML 模板：每次订阅响应都包含统一 `dns`、`proxy-groups`、`rules`。
- 客户端全局 Merge/Script：订阅只负责节点，所有用户安装同一份扩展配置。

Clash/Mihomo 常用方向：

- `dns.enable: true`。
- fake-ip 模式减少系统 DNS 泄漏。
- 国内域名走国内 DoH 或直连 DNS。
- 海外域名和敏感服务域名走带 `#PROXY` 的 DoH。
- 用 external controller 查看 DNS 请求和目标请求实际命中的规则。

客户端 DNS 语义要按客户端文档核对。Stash 这类客户端默认让 DNS 请求直连上游，不会自动按普通代理规则走；把 mihomo 里可用的海外 DoH 或 `#PROXY` 写法照搬过去，可能导致 iOS 上基础 DNS 全超时，表现为 DIRECT、节点测试和网络诊断一起失败。面向中国网络的移动端订阅优先用 1-2 个国内 UDP/system DNS，确认 DNS 诊断通过后再查代理协议兼容。

## 连不上：诊断命令与封锁归属

分清 IP/链路层 vs 协议层（先做这步，再决定要不要碰 Xray）：

- 墙内 TCP 可达性（绕开本机代理/TUN，否则假阳性）：`nc -vz <ip> 443` 再测对照端口 `nc -vz <ip> <ssh-port>`；`ping -c3 <ip>`；`traceroute -n <ip>`（黑洞表现为国际出口后全 `*`）。
- 墙外对照：从一台已有出口的机器或经现有代理测同一 `<ip>:443`，确认服务本身在线。
- 服务端看入站：`ss -tn '( sport = :443 )'`，或 `tcpdump -ni any tcp port 443`，墙内发起时若无任何入站连接 = 包没到。
- 借站 SNI 是否被重置：`echo | openssl s_client -connect <ip>:443 -servername <sni> -tls1_3` 能完成握手 = 该 SNI 未被 RST。

封锁归属（GFW 侧 vs 机房侧），读 KiwiVM API 一手判断，别凭感觉：

- `getLiveServiceInfo`：`ip_nullroutes` 空 + `policy_violation=false` + `suspended=false` + `total_abuse_points=0` ⇒ 机房没动它，封锁在 GFW 侧。
- 机房侧才会出现的信号：`ip_nullroutes` 非空（DDoS/滥用空路由）、`suspended=true`、`policy_violation=true`——这些要走工单/整改，不是换 IP 能解决。

免费换 IP（确认 GFW 侧封锁后）：

- `migrate/getLocations` 列可迁机房；`migrate/start?location=<id>` 触发迁移。保 CN2 GIA 选另一个 CN2GIA 机房。
- 迁移只计流量、几分钟完成；`migrate/start` 偶发 `error 734152`（对本 VPS 暂不可用）是机房侧暂时状态，间隔几分钟重试即可。
- 回收 IP 可能仍被墙，迁完务必复测墙内可达性；脏了再迁，设重试上限避免空耗流量。
- 迁移后 IPv4 变化：同步更新 DNS A 记录、服务端节点 server 字段、面板/订阅访问入口；订阅链接用域名时链接本身不变。

## 验收清单

- 新 SSH 端口可免密登录，旧密码登录不可用。
- 防火墙只开放必要端口。
- 3X-UI 服务 running，面板只能通过预期入口访问。
- 对公网只剩 Reality 端口和对外订阅端口可达；原生订阅端口（由自建服务/反代承接时）从外部连接被拒、只本地可达。
- Reality 端口监听，至少一个 client 能连通目标站。
- 每个用户订阅链接只返回自己的节点。
- Clash/Mihomo 导入后 profile 显示用户名称，不显示 subId。
- DNS 检测不再显示本地运营商 DNS 作为海外解析出口。
- 把一个 client 设为过期或禁用后，该用户失效，其他用户不受影响。
- 续期后该用户恢复。
- 3X-UI 数据库和用户清单已备份。
