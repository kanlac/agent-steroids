---
name: airport-deploy
description: 自建机场（代理服务端）搭建与运维。涵盖 VPS 初始化/加固、3X-UI 面板、Xray VLESS Reality+Vision 入站、多用户独立订阅（UUID/subId/到期/续期）、把节点渲染成 Clash/Mihomo 订阅 YAML、Profile 显示名与到期时间下发、域名/ACME 证书、出口测速、IP 被墙/被滥用风险判断、备份恢复。用户要在 VPS 上部署或维护自建节点/机场、调试 3X-UI 订阅、Reality 入站、订阅链接显示名/到期、面板安全、证书申请、速度低或 IP 风险时用这个 skill。客户端 Clash Verge / mihomo 的配置即代码、规则不命中、DNS 泄漏排查见 clash-verge-config skill。
---

## 这个 Skill 解决什么

自建机场不是单点配置，而是一摞层拼起来：VPS 网络与系统加固、Xray/3X-UI 入站、订阅服务、把节点渲染成客户端能读的订阅 YAML、域名证书、出口 IP 声誉。任何一层错了，用户看到的都只是「不能用」「订阅失败」或「速度很低」。

核心原则：**先分层定位，再改配置；每一层都要有可执行验证。** 不靠客户端截图猜原因，能读服务端运行时状态（服务监听、响应头、证书、解析）就读一手。客户端侧（Clash Verge/mihomo 运行时、规则、DNS）属于 [[clash-verge-config]]。

## 分层心智模型（服务端）

- **VPS/系统层**：SSH 改非默认端口、公钥登录、防火墙只放行必要端口、BBR、服务状态、本机对公网测速。
- **Xray/3X-UI 层**：一台机器一个 VLESS Reality+Vision 入站，所有用户共用入站和 Reality 密钥，每人独立 UUID、subId、到期时间、启用状态。面板优先只监听 `127.0.0.1`，走 SSH 隧道访问；只有订阅端口和 Reality 端口需要公网可达。
- **域名/证书层**：DNS 解析、Cloudflare 只做解析必须灰云、权威解析是否生效、ACME 证书只服务面板和订阅，不参与 Reality 握手。
- **订阅渲染层**：3X-UI 原生订阅常是 base64 裸节点；客户端要远程 YAML 时需服务端渲染成 Clash/Mihomo YAML，并用响应头控制显示名与到期。
- **运营层**：独立订阅链接、到期/续期、泄露换 subId、IP 被墙判断、测速口径、备份恢复。

## 自建 3X-UI + Reality 的落地判断

Reality 直连优先保持简单：借真实大站握手，本身不需要自有域名证书。域名只用于面板后台 HTTPS 和订阅链接 HTTPS（订阅里含 UUID/subId，走 HTTPS 避免被旁路看到）。DNS 或证书暂不可用时可临时用 `http://<SERVER_IP>:<sub-port>/...` 测试，但不要当长期分发方案。

Cloudflare 只做 DNS 时必须灰云。ACME 申请前先确认权威解析和公网解析都指向 VPS；zone 未激活、注册商验证未完成、NS 未切换完成时，在面板里反复点申请证书没有意义。

端口归属要提前规划：**自建订阅服务和 3X-UI 原生订阅不要抢同一端口**。要让自建中间层占对外订阅端口时，先把 3X-UI 原生订阅改到另一个内部端口，再让自建服务监听对外端口。

备份核心是 3X-UI 数据库和用户清单：用户标识、UUID、subId、到期时间、流量策略、当前 Reality 公钥/short-id。详细运维提示见 `references/3x-ui-reality.md`。

## 订阅 YAML 渲染：显示名、到期，与踩过的坑

客户端入口期待远程 YAML 时，自建一个小 HTTP 服务监听订阅端口：按 subId 查用户 → 渲染 Clash/Mihomo YAML → 用响应头控制展示。渲染要同时管好三件事：

- **节点字段完整**：`type: vless`、`tls: true`、`flow: xtls-rprx-vision`、Reality `public-key`/`short-id`/SNI/fingerprint 必须与入站一致。
- **规则和 DNS 集中维护**：把 `dns`/`proxy-groups`/`rules` 写进订阅模板，或让客户端全局 Merge/Script 统一叠加，改一次全员刷新生效。
- **显示名和到期都靠响应头，不是 URL**，这是最容易翻车的地方：

**Profile 显示名** = `Profile-Title: <名>` + `Content-Disposition: attachment; filename=<名>`。
- 坑①：`filename="<名>.yaml"` 这种带引号 + 扩展名的写法，有客户端会把转义后的引号原样显示成 `\"Ab12c.yaml\"`。一律用裸 token：`filename=Ab12c`（无引号、无 `.yaml`）。
- 坑②（关键运维细节）：**改服务端响应头不会自动修好已经导入的旧 profile**。Clash Verge 把解析出的名字缓存在它的 `profiles.yaml` 里，必须让客户端重新拉取一次（强制 auto-update 到期 / 重新导入 / 删除重加）才会更新。验证显示名问题要看客户端实际重拉后的结果，光 `curl` 服务端响应头正确还不够。
- 节点名用 subId 前 5 位（如 `Ab12c`）：跨设备可识别又不露完整 subId，前缀冲突加 `-2/-3` 去重。**节点名要稳定**——别把「剩余 N 天」这类每天变的信息塞进节点名，否则客户端按名字保存的「选中节点」记忆会在改名后丢失。

**到期时间 / 剩余天数** = `Subscription-Userinfo: upload=0; download=0; total=<字节>; expire=<unix 秒>`。expire 由 3X-UI 的 `expiryTime`(毫秒) / 1000 得到；`totalGB=0`（不限量）时省略 `total`，避免客户端算出 0/0 的流量环。Clash Verge 会自动在 profile 卡片上显示到期日期和剩余天数，**完全不用动节点名**。

元方法论：遇到显示名/格式不对，先查一手响应头、看现成可用订阅是怎么配的，不要凭 URL 路径臆测去加 `.yaml` 后缀兼容这类改动——那是把因果搞反，越改越偏。

## 速度与 IP 风险判断

Speedtest 经代理测的是「用户本地网络 → 跨境链路 → VPS → 测速服务器」端到端结果，不等于 VPS 上限。判断瓶颈至少拆三组：VPS 本机对公网测速（机房出口能力）、用户到 VPS 的延迟/丢包/单连接对比（跨境拥塞）、代理后访问目标的实际体验（目标站/规则/DNS）。单用户只跑到几十 Mbps，若 VPS 本机能跑出远高于此的速度，瓶颈多半在用户到机房的链路、运营商国际出口、测速服务器选择或客户端规则，不必直接归咎 VPS。

不建议为「预防封禁」频繁换出口 IP。Reality 直连 IP 的主要风险来自被墙、协议特征被识别、多人滥用高风险服务、公开传播节点、异常扫描流量。只有出现本地连不上 IP、但 VPS 自己出网正常、换网络/地区复核仍不可达时，才考虑换 IP；换后更新 DNS 和服务端记录，订阅链接用域名时可保持不变。
