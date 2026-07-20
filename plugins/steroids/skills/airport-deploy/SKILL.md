---
name: airport-deploy
description: 自建机场（代理服务端）搭建与运维。涵盖 VPS 初始化/加固、3X-UI 面板、Xray VLESS Reality+Vision 入站、多用户独立订阅（UUID/subId/到期/续期）、把节点渲染成 Clash/Mihomo 订阅 YAML、Profile 显示名与到期时间下发、域名/ACME 证书、出口测速、IP 被墙/被滥用风险判断、备份恢复。用户要在 VPS 上部署或维护自建节点/机场、调试 3X-UI 订阅、Reality 入站、订阅链接显示名/到期、面板安全、证书申请、速度低或 IP 风险时用这个 skill。客户端 Clash Verge / mihomo 的配置即代码、规则不命中、DNS 泄漏排查见 clash-verge-config skill。
---

## 这个 Skill 解决什么

自建机场不是单点配置，而是一摞层拼起来：VPS 网络与系统加固、Xray/3X-UI 入站、订阅服务、把节点渲染成客户端能读的订阅 YAML、域名证书、出口 IP 声誉。任何一层错了，用户看到的都只是「不能用」「订阅失败」或「速度很低」。

核心原则：**先分层定位，再改配置；每一层都要有可执行验证。** 不靠客户端截图猜原因，能读服务端运行时状态（服务监听、响应头、证书、解析）就读一手。客户端侧（Clash Verge/mihomo 运行时、规则、DNS）属于 [[clash-verge-config]]。

## 分层心智模型（服务端）

- **VPS/系统层**：SSH 改非默认端口、公钥登录、防火墙只放行必要端口、BBR、服务状态、本机对公网测速。
- **Xray/3X-UI 层**：一台机器一个 VLESS Reality+Vision 入站，所有用户共用入站和 Reality 密钥，每人独立 UUID、subId、到期时间、启用状态。面板优先只监听 `127.0.0.1`，走 SSH 隧道访问；只有订阅端口和 Reality 端口需要公网可达。3X-UI 版本差异会改变数据库关系，改库前先查当前版本源码/表结构，别把生成出的 Xray config 当作唯一事实源。
- **域名/证书层**：DNS 解析、Cloudflare 只做解析必须灰云、权威解析是否生效、ACME 证书只服务面板和订阅，不参与 Reality 握手。
- **订阅渲染层**：3X-UI 原生订阅常是 base64 裸节点；客户端要远程 YAML 时需服务端渲染成 Clash/Mihomo YAML，并用响应头控制显示名与到期。
- **运营层**：独立订阅链接、到期/续期、泄露换 subId、IP 被墙判断、测速口径、备份恢复。

控制面和数据面必须分别验收。订阅服务能返回 YAML，不代表 Xray 入站仍在监听；看到 Cloudflare `521`、节点全超时但订阅正常时，同时核对面板/Xray 服务、实际监听端口和服务退出原因。`Restart=on-failure` 不会拉起一次成功的人工 `stop`，所以要区分 clean stop、崩溃和 OOM，不能只看 unit 是否 enabled。

## 自建 3X-UI + Reality 的落地判断

Reality 直连优先保持简单：借真实大站握手，本身不需要自有域名证书。域名只用于面板后台 HTTPS 和订阅链接 HTTPS（订阅里含 UUID/subId，走 HTTPS 避免被旁路看到）。DNS 或证书暂不可用时可临时用 `http://<SERVER_IP>:<sub-port>/...` 测试，但不要当长期分发方案。

借站域名（`serverNames`/`dest`）的选择判据是「GFW 见到这个 SNI 会不会发 RST」，不是「这站墙内能不能打开」。主动探测器是穿过你这台墙外 VPS 去够借站的，所以借站墙内可不可达与抗探测无关；真正会咬你的是被动 SNI 过滤——若借站 SNI 在 GFW 重置名单上，你自己带这个 SNI 的 Reality 流量会被无差别 RST（与是否识破 Reality 无关）。因此避开 `www.google.com`/`youtube.com` 这类强 SNI 重置域名；`dl.google.com` 属边界可用但不够稳；优先外国、TLS 1.3、明确不被重置的下载/CDN 域名。换 SNI 或上新 IP 后实测确认：对该 IP 发一次该 SNI 的 TLS 握手，能完成 = 没被重置。

Cloudflare 只做 DNS 时必须灰云。ACME 申请前先确认权威解析和公网解析都指向 VPS；zone 未激活、注册商验证未完成、NS 未切换完成时，在面板里反复点申请证书没有意义。

端口归属要提前规划：**自建订阅服务和 3X-UI 原生订阅不要抢同一端口**。要让自建中间层占对外订阅端口时，先把 3X-UI 原生订阅改到另一个内部端口，再让自建服务监听对外端口。

备份核心是 3X-UI 数据库和用户清单：用户标识、UUID、subId、到期时间、流量策略、当前 Reality 公钥/short-id。详细运维提示见 `references/3x-ui-reality.md`。

## 订阅 YAML 渲染：显示名、到期，与踩过的坑

客户端入口期待远程 YAML 时，自建一个小 HTTP 服务监听订阅端口：按 subId 查用户 → 渲染 Clash/Mihomo YAML → 用响应头控制展示。渲染要同时管好三件事：

- **节点字段完整**：`type: vless`、`tls: true`、`flow: xtls-rprx-vision`、Reality `public-key`/`short-id`/SNI/fingerprint 必须与入站一致。
- **逐用户核对事实源**：订阅 HTTP `200` 不证明用户仍启用，也不证明 UUID 正确。3X-UI 版本、迁移脚本和自建渲染器可能让数据库、静态用户清单与 Xray 最终配置漂移；按 `subId → 启用/到期状态 → 渲染 UUID → 实际加载 UUID` 逐用户比对，不能只看总数或集合大部分相交。修正服务端后还要让客户端重新拉取订阅，旧 profile 不会自动换 UUID。
- **规则、DNS 和 TUN 保护集中维护**：把 `dns`/`proxy-groups`/`rules` 写进订阅模板，或让客户端全局 Merge/Script 统一叠加，改一次全员刷新生效。订阅模板还应从本次实际生成的所有节点 `server` 字段推导 `tun.route-exclude-address`：IP 字面量转 `<ip>/32`，域名解析当前 A 记录后逐个转 `/32`。Mihomo/Clash Verge 里，节点域名用 `dns.proxy-server-nameserver` 直连解析，普通 `dns.nameserver` 用带代理组后缀的海外 DoH，避免 DNS leak；Stash 等移动端不要照搬这套 `#PROXY`/`#LEGAL` DNS，按客户端下发兼容模板，否则可能所有节点测速超时。不要维护一份会过期的静态入口 IP 清单；否则 DNS 切换、Cloudflare 边缘变化或前置替换后会把无关旧 IP 下发给用户。
- **显示名和到期都靠响应头，不是 URL**，这是最容易翻车的地方：

**Profile 显示名** = `Profile-Title: <名>` + `Content-Disposition: attachment; filename=<名>`。
- 坑①：`filename="<名>.yaml"` 这种带引号 + 扩展名的写法，有客户端会把转义后的引号原样显示成 `\"Ab12c.yaml\"`。一律用裸 token：`filename=Ab12c`（无引号、无 `.yaml`）。
- 坑②（关键运维细节）：**改服务端响应头不会自动修好已经导入的旧 profile**。Clash Verge 把解析出的名字缓存在它的 `profiles.yaml` 里，必须让客户端重新拉取一次（强制 auto-update 到期 / 重新导入 / 删除重加）才会更新。验证显示名问题要看客户端实际重拉后的结果，光 `curl` 服务端响应头正确还不够。
- 节点名用 subId 前 5 位（如 `Ab12c`）：跨设备可识别又不露完整 subId，前缀冲突加 `-2/-3` 去重。**节点名要稳定**——别把「剩余 N 天」这类每天变的信息塞进节点名，否则客户端按名字保存的「选中节点」记忆会在改名后丢失。

**到期时间 / 剩余天数** = `Subscription-Userinfo: upload=0; download=0; total=<字节>; expire=<unix 秒>`。expire 由 3X-UI 的 `expiryTime`(毫秒) / 1000 得到；`totalGB=0`（不限量）时省略 `total`，避免客户端算出 0/0 的流量环。Clash Verge 会自动在 profile 卡片上显示到期日期和剩余天数，**完全不用动节点名**。

元方法论：遇到显示名、DNS、节点测试或格式不对，先查一手响应头、目标客户端官方文档和客户端日志，再改模板；不要凭 URL 路径臆测去加 `.yaml` 后缀、照搬别的客户端字段，或在没有日志证据时改 Xray 入站参数——那是把因果搞反，越改越偏。

## 连不上的分层诊断：IP 被墙 vs 协议问题

连不上时最贵的错误是直接去调 Xray 版本 / Reality 参数——那是协议层，而死因常在更下面的 IP/链路层。**先分清 TCP 到没到服务器，再决定查哪一层。**

- **墙内 vs 墙外对照**：墙内对 `<ip>:443` 和一个对照端口（SSH）做 TCP 连接测试，同一时刻从墙外（另一条已有代理）测同一地址。墙内全超时 + 墙外通 = IP/端口被封，立即停手，别再碰协议。
- **服务端看入站**：墙内发起时，服务器上 443 若一条入站连接都没有，说明包根本没到，问题在链路不在 Xray。
- **黑洞 vs SNI 过滤要分清**：IP 被黑洞时 ICMP/SSH/443 全死，traceroute 在国际出口（电信 CN2 `59.43.x.x`）之后全 `*`；SNI 过滤只让 TCP 连上、ClientHello 后才 RST，且不影响 ICMP/SSH。两者排查方向完全不同。
- **假阳性陷阱**：做「直连可达」对照时，先确认测试机自己没走代理/TUN，否则流量从代理出口出去，会把「不通」测成「通」。

封锁归属读一手、别猜：KiwiVM `getLiveServiceInfo` 的 `ip_nullroutes` 空 + `policy_violation` false + `suspended` false = 机房没动它，是 GFW 干的（机房侧空路由/滥用停机是另一套处理）。确认 GFW 侧封锁后，注意 **`734152` 死循环**：搬瓦工在 IP 被墙时**禁用该 VPS 的迁移**，`migrate/start` 会持续返回 734152、挂数小时也不恢复——免费迁移换 IP 对被墙 VPS 走不通，别空耗重试。破局：优先**下方 Cloudflare CDN 旁路**（绕过被墙 IP，零成本），或**付费换 IP**（约 $7.39，客户区 `ipchange.php`，非 KiwiVM 面板）。只有 IP **未**被墙时，`migrate/start` 免费迁到另一机房才能换 IP。换 IP/迁移后都要更新 DNS 和服务端记录。诊断命令、黑名单自查、换 IP 步骤见 `references/3x-ui-reality.md`。

**想让被墙 IP 也能用、或换不到干净 IP（含 `734152` 死循环）→ Cloudflare CDN 旁路**：同机加一个 VLESS+WS+TLS 入站（用 Cloudflare 可代理的 HTTPS 端口，非 443），域名转 CF 橙云，客户端经 CF 边缘连入，把被墙的源 IP 藏在背后；订阅端口同样走 CF 可代理端口 + 橙云，墙内才下载得到。直连与 CDN 两节点用 url-test 自动选。可代理端口、`523 = 防火墙没放行回源端口`、渲染器实现坑见 `references/3x-ui-reality.md`。

**预防**：别在 Reality 同一个 IP 上再开明文 HTTP 代理给人用——明文代理是被墙高危行为，会把整个 IP 连坐黑洞，443 上干净的 Reality 一起陪葬。对外只分发 HTTPS 订阅和 Reality/代理入站，不开裸 HTTP 兼容端口；临时 HTTP 迁移窗口结束后必须关开关、重启服务，并用 `ss -lntp` 确认公网地址不再监听，只允许必要的本地回环端口。

## 速度判断

Speedtest 经代理测的是「用户本地网络 → 跨境链路 → VPS → 测速服务器」端到端结果，不等于 VPS 上限。判断瓶颈至少拆三组：VPS 本机对公网测速（机房出口能力）、用户到 VPS 的延迟/丢包/单连接对比（跨境拥塞）、代理后访问目标的实际体验（目标站/规则/DNS）。单用户只跑到几十 Mbps，若 VPS 本机能跑出远高于此的速度，瓶颈多半在用户到机房的链路、运营商国际出口、测速服务器选择或客户端规则，不必直接归咎 VPS。
