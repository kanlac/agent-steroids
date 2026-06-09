---
name: clash-verge-config
description: 以「配置即代码」管理、调试 Clash Verge Rev（mihomo 内核）客户端配置。涵盖：哪些字段扩展脚本能改 / 不能改（external-controller、secret、各端口、log-level 被内核接管）、改了为什么不生效、enhance 管线与字段归属、纯命令行让配置重新生成并生效、mihomo external controller RESTful API、external-ui 自托管面板、判断流量走没走代理 / 命中哪条规则、DNS 泄漏排查、profiles.yaml 里 profile 显示名与到期信息从哪来、远程机器复用本地代理。用户在改 Clash Verge / mihomo 扩展脚本(script) / 扩展配置(merge) / 订阅规则、external-controller / secret / 端口，或抱怨「配置改了不生效」「规则不命中」「远程连不上面板」「DNS 泄漏」「profile 显示名 / 到期不对」「想自动化更新代理配置」时用这个 skill。机场 / 订阅服务端搭建见 airport-deploy skill。
---

## 这个 Skill 解决什么

Clash Verge Rev 是个 Tauri GUI，底层跑 mihomo 内核。它的配置系统有几个**反直觉但有据可查**的行为，不了解会浪费大量时间瞎试。这个 skill 把这些行为的「方向」沉淀下来，让你改配置、做自动化、排查路由时直接走对路，而不是凭印象猜。

核心原则贯穿全篇：**遇到不确定的工具行为，去查一手来源（官方文档 + 源码），不靠猜。** 每条结论都可以、也应该在当前版本上复核。服务端（机场 / 订阅渲染）侧的问题见 [[airport-deploy]]。

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

## DNS 泄漏与分流规则

「DNS 泄漏」通常不是服务端 Reality 参数问题，而是客户端最终运行时配置没接管 DNS，或 DNS 请求走了 DIRECT/系统解析。处理方向：

- 确认最终运行时配置里确实有 `dns.enable: true`，且没被 Clash Verge 的 DNS 设置或全局脚本覆盖。
- 用 fake-ip / redir-host 时都要明确 `nameserver`、`fallback`/`nameserver-policy` 的出口意图；海外 DoH 用 `https://1.1.1.1/dns-query#PROXY` 这类写法强制经代理解析。
- 国内域名走国内 DoH 或直连 DNS，国外域名和 AI 服务域名经代理解析，避免本地运营商 DNS 暴露访问意图。
- 验证别只看检测网页结论，要读 mihomo `GET /connections`、日志和最终配置，确认 DNS 连接命中哪条规则、走哪个出站。

规则同理：从上到下首命中。排查某站没走代理时，找第一条能匹配它的规则，而不是只看最终 IP。

## 远程机器复用本地代理

远程服务器下载海外资源慢时，优先用 SSH reverse tunnel 把远端端口转回本地代理：

```
ssh -f -N -R <remote-port>:127.0.0.1:<local-proxy-port> <remote>
```

判断闭环不要停在「设置了环境变量」：远端用 `curl -x http://127.0.0.1:<remote-port> <url>` 验证目标源可达并测速；本地用 external controller 的 `GET /connections` 或日志确认连接命中预期规则、策略组和出口节点；确定走代理仍慢就切策略组节点重测。对 pip、模型下载、容器拉取等长任务，先确认代理链路和节点质量，再启动大包安装。
