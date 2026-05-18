---
name: check-release
description: Check for Claude Code updates and send release report or Anthropic news via Telegram
---

# Claude Code Release Monitor

检查 Claude Code 是否有版本更新，并通过 Telegram 推送报告。

## 配置

从 `~/.config/claude-release-monitor/` 读取：
- `chat_id` — Telegram 推送目标（纯数字，一行）
- `last-version` — 上次记录的版本号（可能不存在，视为首次运行）

如果 `chat_id` 文件不存在，停止执行，提示用户先配置。

## 检查最新版本

用 WebFetch 请求 `https://registry.npmjs.org/@anthropic-ai/claude-code/latest`，从返回的 JSON 中取 `version` 字段。

与 `last-version` 文件中的版本号对比。

## 情况 A：检测到新版本

1. 用 WebSearch 搜索这个版本的 changelog / release notes（关键词：`Claude Code <version> changelog`、`Claude Code release notes`）
2. 用中文撰写报告：
   - 版本号、发布日期
   - 每个新功能/变更配一个**具体的使用示例**（命令、代码片段、截图描述均可）
   - 值得注意的 bug 修复
3. 将新版本号写入 `last-version` 文件
4. 通过 Telegram 发送报告

## 情况 B：版本未变

1. 用 WebSearch 搜索最近一周的 Anthropic / Claude 相关新闻，包括但不限于：
   - 产品动态、API 变更
   - Anthropic 团队的播客、采访、公开演讲
   - 行业分析、合作伙伴关系
   - 研究论文、官方博客
2. 挑 3-5 条最有趣的，用中文写一份简报
3. 通过 Telegram 发送简报

## Telegram 发送

使用 Telegram reply 工具，参数：
- `chat_id`：从配置文件读取的值
- `text`：报告内容
- `format`：`markdownv2`
- 不设 `reply_to`（这是主动推送，不是回复）

如果报告内容超过 4000 字符，拆分为多条消息发送。

### MarkdownV2 转义规则

Telegram MarkdownV2 对转义要求严格，必须遵守以下规则：

**必须转义的字符**（在普通文本和 `*bold*` 内部）：
`_` `*` `[` `]` `(` `)` `~` `` ` `` `>` `#` `+` `-` `=` `|` `{` `}` `.` `!`
用 `\` 前缀转义，例如 `v2\.1\.81`、`2026\-03\-20`

**例外**：
- `` `code` `` 内部只需转义 `` ` `` 和 `\`，其余字符原样保留
- 中文标点（。、！）不需要转义（非 ASCII）

**排版风格参考**：
```
*Claude Code v2\.1\.81 发布*
2026\-03\-20

*━━━ 新功能 ━━━*

`--bare` *标志* — 自动化利器
说明文本，版本号如 4\.6 需转义。
示例：`claude -p --bare "prompt"`

*━━━ Bug 修复 ━━━*
• 修复某某问题
• 修复另一个问题
```
