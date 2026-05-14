**IMPORTANT**: After any plugin changes, update version in both `plugins/steroids/.claude-plugin/plugin.json` and `plugins/steroids/.codex-plugin/plugin.json` (SemVer: major.minor.patch).

`AGENTS.md` is a symlink to this file. Keep these instructions compatible with both Claude Code and Codex unless a section explicitly names one runtime.

Do not commit unless user asked to.

## README 维护

添加、删除或修改 skill、command、agent、hook、MCP server 时，同步更新 `README.md` 中对应的表格，保持项目介绍与实际内容一致。

Claude Code 和 Codex 都通过 marketplace 暴露 `plugins/steroids/` 作为 `steroids` plugin。正式 runtime skills 只放在 `plugins/steroids/skills/`，不要在根目录维护第二份或用 symlink。Codex manifest 只声明跨运行时稳定可用的 skills；Claude Code 专用的 commands、agents、hooks、MCP server 可放在同一个插件根目录下，但除非确认 Codex 支持对应运行时语义，不要把 Claude Code 专用配置直接挂到 Codex manifest。

## 用户配置文件规范

所有 skill 的用户配置统一存放在一个 JSON 文件中，按 skill 名分 key：
- macOS/Linux: `~/.config/steroids.json`
- Windows: `%APPDATA%\steroids.json`
- Shell 中解析路径: `${APPDATA:-$HOME/.config}/steroids.json`

文档中引用配置路径时**必须同时注明两个平台**，或使用"steroids 配置文件"泛指。

## 公开仓库注意事项

此项目是公开的 Claude Code / Codex 插件仓库。**不要在任何文件中包含**：
- 个人账号、用户名、chat_id、API key
- 私人业务相关的 skill/agent 名称和工作流
- 特定于个人环境的路径（使用 `~` 或 `$HOME` 代替绝对路径）

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
