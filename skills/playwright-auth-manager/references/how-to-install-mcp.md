# How to Install MCP

- 建议安装在项目目录下
- 不同客户端的配置路径和安装方式都不一样
- 下面给出了 Claude Code 和 OpenCode 的配置方式，对于其它客户端，给出参考，建议用户自行配置

Claude Code 参考配置 {PROJECT_ROOT}/.mcp.json:
```
{
    "mcpServers": {
        "playwright-localhost3000-user1": {
            "command": "npx",
            "args": [
                "@playwright/mcp@latest",
                "--isolated",
                "--storage-state=~/myproject/.playwright-auth/localhost3000-user1.json"
            ]
        }
    }
}
```

OpenCode 参考配置 {PROJECT_ROOT}/opencode.json:
```
{
    "$schema": "https://opencode.ai/config.json",
    "mcp": {
        "playwright-xiaohongshu-alice": {
            "command": [
                "npx",
                "@playwright/mcp@latest",
                "--isolated",
                "--storage-state=~/myproject/.playwright-auth/xiaohongshu-auth.json"
            ],
            "type": "local"
        }
    },
}
```