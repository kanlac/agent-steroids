# Bun Proxy + ReadableStream Body 文件上传 Bug 调研

> 日期：2026-03-29

## 背景

Claude Code 的 Telegram plugin 使用 grammy 库与 Telegram Bot API 通信。在 HTTP 代理环境下，文本消息正常发送，但文件上传（sendDocument、sendPhoto 等）失败：

```
Network request for 'sendDocument' failed!
The socket connection was closed unexpectedly.
```

## 根因分析

### grammy 的 multipart 实现

grammy 发送文件时不用原生 `FormData`，而是自行构造 multipart/form-data 作为 `ReadableStream`（async iterator → stream）。原因：

1. **流式传输**：文件逐块发送，不全量缓冲到内存，大文件时必要
2. **跨运行时兼容**：统一 Node、Deno、Web/Edge 行为，各平台原生 FormData 行为不一致
3. **自定义 InputFile 抽象**：支持文件路径、URL、Buffer、流、异步迭代器多种来源

相关代码：`grammy/out/core/payload.js` 的 `createFormDataPayload()` → `payloadToMultipartItr()` → `itrToStream()`

### Bun 的 TLS 排序 Bug

Bun 的 fetch 在通过 HTTP CONNECT proxy tunnel 发送 ReadableStream body 时，会交错直接 socket 写入和缓冲的加密字节，导致 TLS 记录乱序。代理检测到 MAC 不匹配后断开连接。

**复现条件**：Bun fetch + HTTP proxy + ReadableStream body（或大请求体 >20MB）

**对比验证**：

| Body 类型 | 通过 Bun proxy | 结果 |
|---|---|---|
| JSON 字符串（sendMessage） | ✅ | 正常 |
| 原生 FormData | ✅ | 正常 |
| ReadableStream（grammy multipart） | ❌ | socket 关闭 |

去掉代理后的错误变为 `unknown certificate verification error`（无法直连 Telegram API），确认代理是必须的。

## 上游 Issue

- **主 Issue**: [oven-sh/bun#17434](https://github.com/oven-sh/bun/issues/17434)
  - 报告者复现环境：Bun 1.2.2 ~ 1.2.22（Linux/macOS）
  - 修复 PR [#22417](https://github.com/oven-sh/bun/pull/22417)（TLS record ordering）和 [#23719](https://github.com/oven-sh/bun/pull/23719)（EOF handling）已合并
  - **问题在 Bun 1.3.0+ 仍然复现**（@codebykenny 确认）
  - 我们在 Bun 1.3.11 确认复现
- 相关 meta issue: [oven-sh/bun#28396](https://github.com/oven-sh/bun/issues/28396)（node:http 对 proxy 基本不可用）
- 相关 WebSocket 回归: [oven-sh/bun#28599](https://github.com/oven-sh/bun/issues/28599)

## 社区认可的 Workaround

来源：oven-sh/bun#17434 评论区

由 Bun 仓库 contributor @avarayr 提出，@codebykenny 在 Bun 1.3.0 确认有效，Bun 官方成员 @cirospaciari 参与讨论：

使用 [undici](https://github.com/nodejs/undici)（Node.js 官方 HTTP 客户端库）的 `fetch` + `ProxyAgent` 替代 Bun 原生 fetch 来发送文件。

```typescript
import { fetch, ProxyAgent } from "undici";
const dispatcher = new ProxyAgent("http://127.0.0.1:7890");
await fetch(url, { method: "POST", body: formData, dispatcher });
```

## 一键复现

验证 Bun 新版本是否修复此 bug 的脚本见 telegram-channel skill 的 `scripts/test-bun-proxy-stream.sh`。
