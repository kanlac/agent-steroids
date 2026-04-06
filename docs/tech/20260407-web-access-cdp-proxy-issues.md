# web-access skill CDP Proxy 端口发现问题

> 日期：2026-04-07  
> 测试版本：web-access v2.4.2
> 环境：macOS, Chrome 146, Node.js 25

## 概述

CDP Proxy 的 `discoverChromePort()` 在用户日常 Chrome 运行的环境下无法正确发现通过 `--remote-debugging-port` 启动的 Chrome 实例。以下是三个具体问题及建议修复方案。

## 问题 1：TCP 探测无法区分可用的 CDP 端口

**文件**：`scripts/cdp-proxy.mjs` 第 95-101 行

**现状**：`checkPort()` 使用 `net.createConnection` 做 TCP 探测，只要端口在监听就返回 true。

**问题**：用户日常 Chrome（未带 `--remote-debugging-port` 启动）会在 `DevToolsActivePort` 文件中记录一个内部调试端口。该端口确实在监听 TCP 连接，但**不提供 CDP HTTP API**——所有 `/json/*` 端点返回 404。

实测对比：

```
# 日常 Chrome（无 --remote-debugging-port）的 DevToolsActivePort 端口
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9222/json/version
404

# --remote-debugging-port 启动的 Chrome
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9224/json/version
200
```

TCP 探测无法区分这两种情况，导致 Proxy 锁定在日常 Chrome 的端口上，WebSocket 连接随后失败（需要 `chrome://inspect#remote-debugging` 授权），进入重试死循环。后备端口扫描永远执行不到。

**建议修复**：用 HTTP `GET /json/version` 替代 TCP 探测。返回 200 才认为是可用的 CDP 端口。

```javascript
async function checkPort(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/json/version`, {
      signal: AbortSignal.timeout(2000),
    });
    return res.ok;
  } catch {
    return false;
  }
}
```

这样 DevToolsActivePort 中的非 CDP 端口会被正确跳过，Proxy 可以继续后备扫描或报错。

**担忧回应**：原代码注释说"避免 WebSocket 连接触发 Chrome 安全弹窗"。HTTP GET 不是 WebSocket 连接，不会触发授权弹窗，且能准确判断端口是否提供 CDP API。

## 问题 2：硬编码端口列表可用进程发现替代

**文件**：`scripts/cdp-proxy.mjs` 第 81 行

**现状**：`commonPorts = [9222, 9229, 9333]`，逐个 TCP 探测。

**问题**：
- 用户的 `--remote-debugging-port` 不在列表中则发现不到（如 9224）
- 列表中的端口可能被无关进程占用，产生误连
- 随着更多 skill/工具使用 CDP Chrome，端口冲突概率增大

**建议修复**：从进程列表确定性地发现所有 Chrome 调试端口。

```javascript
import { execSync } from 'node:child_process';

function discoverRemoteDebuggingPorts() {
  try {
    const out = execSync(
      "ps ax -o command | grep -o '\\-\\-remote-debugging-port=[0-9]*' | sed 's/.*=//'",
      { encoding: 'utf-8', timeout: 3000 },
    );
    return [...new Set(out.trim().split('\n').filter(Boolean).map(Number))];
  } catch {
    return [];
  }
}
```

进程列表是确定性来源：只有实际运行中的、带 `--remote-debugging-port` 参数的 Chrome 才会被发现。可作为 DevToolsActivePort 之后、硬编码列表之前的优先级，或直接替代硬编码列表。

## 问题 3：支持用户指定端口

**现状**：`CDP_PROXY_PORT` 环境变量控制 Proxy 自身的监听端口，但没有环境变量控制要连接的 Chrome 端口。

**场景**：用户已知 Chrome 调试端口（如通过配置文件管理），希望跳过自动发现直连。

**建议**：增加 `CDP_CHROME_PORT` 环境变量，在 `discoverChromePort()` 最前面检查：

```javascript
async function discoverChromePort() {
  const envPort = parseInt(process.env.CDP_CHROME_PORT);
  if (envPort > 0 && envPort < 65536) {
    const ok = await checkPort(envPort);
    if (ok) {
      console.log(`[CDP Proxy] 使用环境变量 CDP_CHROME_PORT=${envPort}`);
      return { port: envPort, wsPath: null };
    }
    console.log(`[CDP Proxy] CDP_CHROME_PORT=${envPort} 未响应，回退自动发现`);
  }
  // ... 原有逻辑
}
```

## 补充背景：Chrome 136+ 的变化

Chrome 136 起，`--remote-debugging-port` 在默认 user data 目录上不再生效（安全考虑），必须搭配 `--user-data-dir` 指向非默认目录。macOS 也没有持久化 Chrome 启动参数的原生机制（无 `defaults write` 支持）。

这意味着 skill 文档中"直连用户日常 Chrome，天然携带登录态"的使用模式，在 Chrome 136+ 上需要用户使用独立 profile 的 Chrome 实例——不再是"日常 Chrome"本身。建议在 skill 文档中更新相关说明。
