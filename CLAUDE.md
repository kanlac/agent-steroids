**IMPORTANT**: After any plugin changes, update version in `.claude-plugin/plugin.json` (SemVer: major.minor.patch).

Do not commit unless user asked to.

## 文档组织（docs/）

- [`docs/research/`](./docs/research/)：调研、对比分析、信息源
- [`docs/tech/`](./docs/tech/)：技术方案、架构设计、验证计划

文档约定：
- 文件名统一使用日期前缀 `YYYYMMDD-`，便于按时间排序

## Hooks

### guard-payload-size

临时方案：在 session payload 接近 20MB API 限制时触发告警，提示执行 `/compact`。通过 `transcript_path` 检查对话文件大小，超过 16MB 时通过 stderr（CLI 可见）和 systemMessage（agent 可见）同时告警。

- 相关 issue：[anthropics/claude-code#8092](https://github.com/anthropics/claude-code/issues/8092)（主 issue）、[#37418](https://github.com/anthropics/claude-code/issues/37418)（MCP 截图触发）、[#26018](https://github.com/anthropics/claude-code/issues/26018)（Read 工具触发）
- 官方修复后可移除
