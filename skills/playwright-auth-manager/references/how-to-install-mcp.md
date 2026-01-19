# How to Install MCP

## Overview

本指南介绍如何在不同 MCP 客户端中配置 Playwright MCP Server。

**核心原则：**
- MCP 配置使用 **用户级别**（user scope），跨项目共享
- 认证文件统一存放在 `~/.config/playwrightAuth/` 目录
- MCP 服务器命名规范：`playwright-{domain}-{user}`
- 认证文件命名规范：`{domain}-{user}.json`

**优势：**
- 认证文件跨项目共享，无需重复配置
- 不污染项目目录，无需添加 .gitignore
- 一次配置，所有项目可用

**不同客户端的配置文件位置和格式不同**，下面提供了常见客户端的配置示例。对于其他客户端，请参考其文档并遵循上述命名规范。

## Claude Code

**配置文件位置：** `~/.claude.json`

### 单会话配置

在 `~/.claude.json` 的 `mcpServers` 下添加配置：

```json
{
  "mcpServers": {
    "playwright-localhost3000-jack": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/localhost3000-jack.json"
      ]
    }
  }
}
```

**注意：**
- 请将 `/Users/yourname` 替换为你的实际用户目录路径
- `--storage-state` 必须使用**绝对路径**，相对路径可能导致问题

### 多会话配置

```json
{
  "mcpServers": {
    "playwright-localhost3000-jack": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/localhost3000-jack.json"
      ]
    },
    "playwright-localhost3000-alice": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/localhost3000-alice.json"
      ]
    },
    "playwright-github-bob": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/github-bob.json"
      ]
    }
  }
}
```

### 自动保存会话

添加 `--save-session` 标志以自动保存会话变更：

```json
{
  "mcpServers": {
    "playwright-localhost3000-jack": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/localhost3000-jack.json",
        "--save-session"
      ]
    }
  }
}
```

## OpenCode

**配置文件位置：** `~/.config/opencode/opencode.json` 或 `~/.config/opencode/opencode.jsonc`（检查哪个路径存在）

### 单会话配置

在配置文件的 `mcp` 下添加配置：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "playwright-localhost3000-jack": {
      "command": [
        "npx",
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/localhost3000-jack.json"
      ],
      "type": "local"
    }
  }
}
```

**注意：**
- 请将 `/Users/yourname` 替换为你的实际用户目录路径
- `--storage-state` 必须使用**绝对路径**，相对路径可能导致问题

### 多会话配置

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "playwright-localhost3000-jack": {
      "command": [
        "npx",
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/localhost3000-jack.json"
      ],
      "type": "local"
    },
    "playwright-localhost3000-alice": {
      "command": [
        "npx",
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/localhost3000-alice.json"
      ],
      "type": "local"
    },
    "playwright-github-bob": {
      "command": [
        "npx",
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/github-bob.json"
      ],
      "type": "local"
    }
  }
}
```

### 自动保存会话

添加 `--save-session` 标志以自动保存会话变更：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "playwright-localhost3000-jack": {
      "command": [
        "npx",
        "@playwright/mcp@latest",
        "--isolated",
        "--storage-state=/Users/yourname/.config/playwrightAuth/localhost3000-jack.json",
        "--save-session"
      ],
      "type": "local"
    }
  }
}
```

## 其他客户端

对于其他 MCP 客户端（如 Cline、Continue 等），请参考其文档配置 MCP 服务器。

**关键配置要素：**
1. **命令：** `npx @playwright/mcp@latest`
2. **参数：**
   - `--isolated`: 使用隔离的浏览器上下文
   - `--storage-state=/absolute/path/to/{domain}-{user}.json`: 认证文件**绝对路径**（必须使用绝对路径）
   - `--save-session`（可选）: 自动保存会话变更
3. **服务器名称：** `playwright-{domain}-{user}`
4. **配置级别：** 使用用户级别配置（user scope），而非项目级别

## 命名规范详解

### MCP 服务器名称

格式：`playwright-{domain}-{user}`

- **domain**: 目标网站/服务标识符
  - 示例：`localhost3000`（本地开发）、`github`、`xiaohongshu`
  - 建议使用小写字母和数字，不含特殊字符
- **user**: 用户/账户标识符
  - 示例：`jack`、`alice`、`user1`
  - 建议使用小写字母和数字，不含特殊字符

### 认证文件名称

格式：`{domain}-{user}.json`

存放路径：`~/.config/playwrightAuth/{domain}-{user}.json`

**示例：**
- `~/.config/playwrightAuth/localhost3000-jack.json`
- `~/.config/playwrightAuth/github-alice.json`
- `~/.config/playwrightAuth/xiaohongshu-bob.json`

## 配置后续步骤

1. **重启 MCP 客户端** 以加载配置

2. **验证配置** 通过访问受保护页面验证认证是否生效

## 常见问题

### Q: 为什么使用 `--isolated` 参数？

A: `--isolated` 创建一个干净的浏览器上下文，只加载认证数据，不包含其他浏览历史或扩展。这样可以：
- 减小文件体积（5-50KB vs 50-500MB）
- 加快启动速度
- 更适合版本控制

### Q: 什么时候使用 `--save-session`？

A: 当你希望会话期间的认证变更（新 cookies、localStorage 更新）自动保存时使用。适用于：
- 频繁过期的会话
- 需要持续更新的认证状态

### Q: 如何切换不同的会话？

A: 配置多个 MCP 服务器实例，使用不同的工具前缀：
```javascript
// 使用 Jack 的会话
await mcp__playwright-localhost3000-jack__browser_navigate({ url: "..." });

// 切换到 Alice 的会话
await mcp__playwright-localhost3000-alice__browser_navigate({ url: "..." });
```

## 相关文档

- **[usage-guide.md](./usage-guide.md)** - Playwright MCP 使用指南
- **[../SKILL.md](../SKILL.md)** - Playwright Auth Manager 完整文档
