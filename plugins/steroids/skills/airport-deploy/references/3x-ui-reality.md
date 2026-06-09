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
