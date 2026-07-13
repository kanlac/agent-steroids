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
- `expiryTime`: 到期时间；通过面板或 API 续期时，本质上只改变这个业务字段。
- `enable`: 停用用户时优先关 enable 或删除该 client。

3X-UI 的持久化模型会随版本演进，遇到「面板有用户但生成的 Xray config 里 `clients` 为空」之类问题，先确认当前版本源码和数据库关系，而不是直接改生成文件。以 3X-UI v3.2.x 为例，client 与 inbound 的关系由 `client_inbounds` 表维护，生成 Xray config 时再从该表关联 client；只改 `inbounds.settings` 可能会被重生成覆盖。修复顺序应是停服务、备份数据库、补齐权威关系表、重启后验证生成 config 和实际端口。更稳的做法：有面板 API Token 时直接用 API（`Authorization: Bearer <token>` 调 `/<webBasePath>/panel/api/inbounds/*`）建 inbound/client，由面板维护全部关系表，避免手搓漏表；v3.3.x 进一步把 client 拆进独立 `clients` 表，手改更易出错。

**续期 / 恢复用户不要只改一张表。** 优先走面板或 API，让 3X-UI 自己同步各持久化位置。必须手改 SQLite 时，先停 `x-ui` 并备份 `/etc/x-ui/x-ui.db`，然后按当前 schema 同步检查这些位置：`clients.enable` / `clients.expiry_time`、对应 `inbounds.settings` 里每个匹配 client 的 `enable` / `expiryTime`、以及 `client_traffics.enable` / `client_traffics.expiry_time`。有多个入站（例如 Reality 直连 + WS/CDN）时，所有含该用户的入站 settings 都要同步；否则数据库看似已续期，生成的 Xray config 仍可能没有这个用户。

续期验收不能只看 SQL 查询结果。重启 `x-ui` 后确认 `/usr/local/x-ui/bin/config.json` 或实际生成配置中包含该 client，`x-ui` / 订阅服务 active，订阅响应头的 `Subscription-Userinfo expire=<unix 秒>` 已更新；最后让客户端刷新订阅并实测工作节点。若自建订阅服务启动时缓存了用户清单，续期后还要重启订阅服务或触发其重新加载。

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
- 节点 `server` 是域名时，给 `dns.proxy-server-nameserver` 配直连可达 DNS，专门解析代理服务器域名；普通 `dns.nameserver` 用带 `#PROXY` 的海外 DoH，避免 DNS leak 检测显示国内解析器出口。
- 国内域名走国内 DoH 或直连 DNS。
- 海外域名和敏感服务域名走带 `#PROXY` 的 DoH。
- 用 external controller 查看 DNS 请求和目标请求实际命中的规则。

客户端 DNS 语义要按客户端文档核对。Stash 这类客户端默认让 DNS 请求直连上游，不会自动按普通代理规则走；把 mihomo 里可用的海外 DoH 或 `#PROXY` 写法照搬过去，可能导致 iOS 上基础 DNS 全超时，表现为 DIRECT、节点测试和网络诊断一起失败。服务端订阅渲染器应按 User-Agent、路径或显式参数分模板：桌面 Mihomo 追求 DNS leak 防护，Stash 移动端优先使用其官方支持的直连 DNS 字段恢复可用性。

## 连不上：诊断命令与封锁归属

分清 IP/链路层 vs 协议层（先做这步，再决定要不要碰 Xray）：

- 墙内 TCP 可达性（绕开本机代理/TUN，否则假阳性）：`nc -vz <ip> 443` 再测对照端口 `nc -vz <ip> <ssh-port>`；`ping -c3 <ip>`；`traceroute -n <ip>`（黑洞表现为国际出口后全 `*`）。
- 墙外对照：从一台已有出口的机器或经现有代理测同一 `<ip>:443`，确认服务本身在线。
- 服务端看入站：`ss -tn '( sport = :443 )'`，或 `tcpdump -ni any tcp port 443`，墙内发起时若无任何入站连接 = 包没到。
- 借站 SNI 是否被重置：`echo | openssl s_client -connect <ip>:443 -servername <sni> -tls1_3` 能完成握手 = 该 SNI 未被 RST。

封锁归属（GFW 侧 vs 机房侧），读 KiwiVM API 一手判断，别凭感觉：

- `getLiveServiceInfo`：`ip_nullroutes` 空 + `policy_violation=false` + `suspended=false` + `total_abuse_points=0` ⇒ 机房没动它，封锁在 GFW 侧。
- 机房侧才会出现的信号：`ip_nullroutes` 非空（DDoS/滥用空路由）、`suspended=true`、`policy_violation=true`——这些要走工单/整改，不是换 IP 能解决。

换 IP / 迁移机房（`734152` 死循环陷阱）：

- **`734152`「Migration backend not available for this VPS」根因通常是 IP 被墙**——搬瓦工在 IP 被墙时禁用该 VPS 的迁移。死循环：想靠迁移换掉被墙 IP，而"被墙"正是迁移被禁的原因；`migrate/start` 会一直返回 734152、挂数小时也不恢复，**重试无用**，别让循环空耗。
- 确认 IP 是否被墙：KiwiVM 黑名单工具 `https://kiwivm.64clouds.com/main-exec.php?mode=blacklistcheck` 点 Test，`IP BLOCKED` 即被墙。
- **破局两条路**：① **Cloudflare CDN 旁路**（见下节）——不换 IP，把被墙源 IP 藏到 CF 后面，被墙也能用、零成本，通常首选；② **付费换 IP**：客户区（非 KiwiVM 面板）`ipchange.php` → 选该 VPS → `Request IP Change` → 在 Billing/My Invoices 付约 $7.39（支付宝/PayPal/银联）→ 几分钟~24h 自动分配随机新 IP（官方验证大陆可访问）；新 IP 若仍脏，开工单要求再换。免费换 IP 早已取消。
- **IP 未被墙时**才能用免费迁移换 IP：`migrate/start?location=<id>` 迁到另一机房即得新 IP（只计流量、几分钟完成），CN2 GIA 套餐可在多机房间切。
- 换 IP / 迁移后 IPv4 变化：同步更新 DNS A 记录、服务端节点 server 字段、面板/订阅入口；订阅链接用域名时链接本身不变。

## Cloudflare CDN 旁路（源 IP 被墙、又拿不到干净 IP 时的兜底）

迁移/换 IP 拿不到干净 IP，或想让"被墙也能用"，就把源 IP 藏到 Cloudflare 后面：

- **架构**：同机保留 Reality/443（直连）+ 新增一个 VLESS+WS+TLS 入站（CDN）；域名转 Cloudflare 橙云；客户端 CDN 节点连 `域名:<CDN端口>`，经 CF 边缘转发到源站。CF 边缘 IP 没被墙，等于把被墙的源 IP 藏起来。
- **端口必须是 Cloudflare 可代理的 HTTPS 端口**：`443 / 2053 / 2083 / 2087 / 2096 / 8443`。443 给 Reality，CDN 入站和订阅服务各从剩下的里挑一个空闲端口（端口号无所谓，可代理且空闲即可）。
- **订阅端口也要走 CF 橙云**：否则订阅域名仍解析到被墙源 IP，墙内下载不到订阅。
- **523 Origin Unreachable = 源站防火墙没放行 CDN/WS 端口给 Cloudflare**。CF 边缘可达（TLS 握手能成）不代表 CF 够得到源站；务必在源站防火墙（firewalld/ufw/iptables）开放该端口。判据：墙内对该端口经 CF 返回 523 而非超时，就去查防火墙；`nc` 从外部测通只证明 CF 边缘、不证明回源。
- 订阅里直连 + CDN 两节点放进 url-test 自动选：源 IP 通时走直连（延迟低），被墙时直连超时、自动切 CDN。
- 证书：CDN 入站和订阅服务用源站真实证书。新机签证书可 acme.sh standalone HTTP-01——先让域名**灰云**解析到源站、放行 80 签发，再转橙云；橙云后续续期改 DNS 模式或临时灰云。

## 渲染器（自建订阅服务）实现坑

- **响应头里的 emoji/中文会让 Python `http.server` 崩**：它按 latin-1 编码头部，非 latin-1 字符抛异常、整条订阅返回空。`Profile-Title` 等值用 `value.encode("utf-8").decode("latin-1")` 把 UTF-8 字节偷渡过去（客户端按 UTF-8 解）；`Content-Disposition` 的 filename 保持纯 ASCII（空格/emoji 会破坏头部解析）。
- **渲染器调外部 API 用 `curl`，别用 `urllib`**：Python urllib 的 HTTPS 证书校验在不少机器上失败（CA bundle 与系统不一致），curl 用系统 CA 正常。`subprocess.run(["curl","-s",url])` 更稳；外部 API 结果加几分钟缓存，避免每次订阅请求都打。
- **信息展示节点（到期/用量）**：想在订阅里显示到期时间、个人/服务器用量，桌面 Mihomo/Clash Verge 可做成"节点"放进选择组列表里——本质是工作节点（CDN）的克隆，测速显示真实延迟、不超时、不产生多余的组卡片。Stash 等移动端兼容性更差，不要把信息节点伪装成真实 VLESS 下发；否则它会参与测速并把信息项也标成失败。移动端优先依赖 `Subscription-Userinfo` 响应头或单独客户端模板。
- **用量数据源**：个人用量 = `client_traffics` 里该用户跨入站的 email（含 CDN 入站的 email 变体）up+down 合计；服务器总用量优先用机房 API（Bandwagon 用 KiwiVM `data_counter`/`plan_monthly_data`，精确），无机房 API 时退用 `vnstat`（只从安装时刻起计，会少算本月已用）。
- **订阅 YAML 顶层下发 TUN 入口排除**：遍历本次实际渲染出的所有工作节点和信息节点的 `server` 字段，IP 字面量直接渲染为 `<ip>/32`，域名则解析当前 A 记录后逐个渲染为 `/32`，写入 `tun.route-exclude-address`。这不是只给本机 Clash Verge 的增强脚本做的优化，而是订阅本身的安全兜底：用户环境开启 TUN/fake-ip 时，如果连接节点入口的流量被 TUN 捕获，会形成自回环并表现为节点 timeout。不要维护一份静态入口 IP 清单；DNS 切换、Cloudflare 边缘变化、前置替换后，静态清单会继续下发已经不对应当前节点 server 的旧 IP。
- **订阅 YAML 分离普通 DNS 与代理服务器 DNS**：只要节点 `server` 是域名，就给 `dns.proxy-server-nameserver` 留一条直连 DNS 通道；普通 `dns.nameserver` 用带代理组后缀的海外 DoH。否则模板里 `fallback: ...#PROXY` / `...#LEGAL` 这类海外 DoH 会在节点尚未连上时反过来依赖该节点，mihomo 日志常见 `dns resolve failed`；但如果普通 `nameserver` 直连国内 DoH，又会在 DNS leak 检测里暴露国内解析器出口。
- **订阅 YAML 顶层下发 `ipv6: false`**：避免客户端解析 AAAA 走 IPv6 直连绕过代理（IPv6 路由泄露的一般卫生）。注意：地理严格的站（Gemini）报 not supported **多半是出口 IP 被 Google 标错国**（机房 IP 常被标成 CHN，哪怕物理在美国），先用 gemini 检测法验出口 IP 的 Google 地理，别先怀疑泄露——详见 [[clash-verge-config]]。

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
