---
name: line-quality-audit
description: Evaluate VPS, proxy server, and commercial airport node quality for China-facing use. Use when comparing VPS providers or proxy nodes, diagnosing whether a route is CN2 GIA/CTGNet/9929/CMI or ordinary transit, checking packet loss/latency/jitter/single-thread throughput, validating IP blocking risk, and verifying whether Google geolocation misclassifies the exit IP.
---

## 目标

这个 skill 用于评估 VPS 或机场节点的真实线路质量，尤其是中国大陆用户访问海外节点时的体验。核心原则是：**先分方向识别线路，再测质量，再看真实吞吐和服务可用性，最后评估 IP 风险与购买决策**。

如果需要输出正式报告，先读取 `references/report-template.md`，按模板组织结果。

## 先分清测试对象

- **可登录 VPS**：可以测本地去程、VPS 回程、VPS 自身出口、服务端资源、端口可达性、代理后体感。
- **不可登录机场节点**：只能测客户端视角，包括节点延迟、经代理下载、出口 IP、Google 地理、目标站可用性；不能对服务端回程下强结论。
- **CDN 中转节点**：客户端看到的是 CDN 边缘，不能用域名 `traceroute` 证明源站线路；要把“源 IP 直连”和“CDN 中转”分开评价。

## 线路识别口径

`traceroute` / `mtr` 的方向由发起点决定：

- 本地到 VPS：本地运行 `traceroute <VPS_IP>`，看去程。
- VPS 回国内：VPS 上运行 `traceroute <国内目标>` / `mtr <国内目标>`，看回程。
- VPS 到海外目标：VPS 上运行 `curl` / `ping` / `mtr`，看机房出口。

商家宣传“9929 / CN2 GIA / CMI”时，必须确认它指的是去程、回程还是双向。用户本地去程没看到 AS9929，不能直接证明商家虚假宣传；验证回程承诺，要在 VPS 上对国内电信、联通、移动、阿里、腾讯、百度等目标分别跑 `traceroute` / `mtr`。看到部分目标不走宣传线路，也不必马上定性为欺骗；更精确的结论是“哪些目标、哪个方向、哪一段走了宣传线路”。

常见线路线索：

| 线路 | 常见特征 | 含义 |
|---|---|---|
| 电信 163 / ChinaNet | AS4134、`202.97.*` | 普通电信国际公网，晚高峰容易拥塞 |
| CN2 GIA | AS4809、常见 `59.43.*` | 电信高端线 |
| CTGNet | AS23764 | 电信国际新骨干，常与 CN2 GIA 并列销售 |
| 联通 9929 / CUII | AS9929、常见 `218.105.*` | 联通高端线 |
| 联通普通 | AS4837、`219.158.*` | 普通联通国际/国内骨干 |
| 移动 CMI | AS58453、AS9808 等 | 移动国际出口 |
| 海外普通 Transit | GTT、Cogent、NTT、Telia 等 | 不等于回国优化 |

## 质量指标

优先看最终目标，不要被中间节点的 ICMP 限速误导。某一跳 90% 丢包但后续和最终目标正常，通常不是业务丢包；从某一跳开始后续全部变差，才说明链路问题可能持续传导。

评分重点：

- **丢包**：最终目标 0% 理想，<1% 很好，1-3% 可用但可能卡，3-5% 明显不稳，>5% 不适合主力。
- **延迟**：美国西海岸 130-220ms 通常合理；香港/日本低延迟但晚高峰抖动大时不一定更好。
- **抖动**：`mtr` 的 `StDev` 或 `ping` 的 `stddev`，<10ms 很稳，10-30ms 正常，30-80ms 偏差，>80ms 不适合主力。
- **单线程吞吐**：比多线程 speedtest 更接近日常网页、视频首包、Git/API 体感。
- **晚高峰稳定性**：20:00-24:00 和周末晚高峰权重最高；白天数据只能做基线。
- **端口/IP 风险**：源 IP 的 443/SSH/订阅端口是否可达，是否有 CDN fallback，是否能换 IP。

## 必测项

可登录 VPS：

```bash
# 本地去程
traceroute -n "$VPS_HOST"
mtr -rwzc 100 "$VPS_HOST"
ping -c 50 "$VPS_HOST"
nc -vz -G 5 "$VPS_HOST" 443

# VPS 回程，目标要覆盖不同网络
for t in 223.5.5.5 114.114.114.114 119.29.29.29 180.76.76.76 202.96.209.133; do
  traceroute -n -w 2 -q 1 -m 20 "$t"
  mtr -rwzc 30 "$t"
done

# VPS 自身出口
curl -L -o /dev/null -w 'time_total=%{time_total} speed_download=%{speed_download}\n' \
  --connect-timeout 10 --max-time 60 \
  'https://speed.cloudflare.com/__down?bytes=10000000'
```

客户端/机场节点：

```bash
# 经指定本地代理端口测出口和单线程吞吐
curl -fsSL --max-time 10 -x http://127.0.0.1:7890 https://api.ipify.org
curl -L -o /dev/null -w 'time_total=%{time_total} speed_download=%{speed_download}\n' \
  --connect-timeout 10 --max-time 60 \
  -x http://127.0.0.1:7890 \
  'https://speed.cloudflare.com/__down?bytes=10000000'
```

使用 Clash Verge / mihomo 时，用 external controller 临时切节点、测完恢复。不要把临时选择当成配置变更；报告里记录原策略组和恢复情况。

## Google 地理误判

Google 有自己的 IP 地理库，和 ipinfo、ip-api、MaxMind 经常不一致。很多 Google 服务按 Google 自己的判定决定是否可用；如果 Google 把美国/新加坡等出口误判为中国，这是明确减分项，即使普通 IP 库显示正常。

经被测节点运行：

```bash
r=$(curl -fsSL --max-time 20 -A 'Mozilla/5.0' -x http://127.0.0.1:7890 'https://gemini.google.com/')
ip=$(curl -fsSL --max-time 10 -x http://127.0.0.1:7890 'https://api.ipify.org')
cc=$(printf '%s' "$r" | grep -aoE ',2,1,200,"[A-Z]{2,3}"' | head -1 | sed -E 's/.*"([A-Z]{2,3})"/\1/')
printf 'exit_ip=%s\ngoogle_country=%s\n' "$ip" "${cc:-unknown}"
```

解读：

- `google_country` 等于购买目标国家/地区：加分。
- `google_country=CHN` 或 Gemini 返回明显不可用：减分；先怀疑 Google 地理误判，不要先改客户端规则。
- `unknown`：不能下结论；记录为未判定，并补充 Gemini 页面是否可用、HTTP 是否被重定向或拦截。

## 结论写法

结论要写成“适合什么、不适合什么”，不要只写好/差。示例：

- “源 IP 直连延迟低但单线程吞吐差，适合探活备用，不适合作主力。”
- “CDN 中转延迟高但吞吐更稳，适合日常网页/下载，不适合实时交互。”
- “回程部分目标走 AS9929，但去程仍走普通电信 163；不能称为双向全程 9929。”
- “机场节点无法登录服务端，不能评价 VPS 回程，只能评价客户端体感和出口可用性。”
