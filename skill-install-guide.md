# Skill 安装指南

从 GitHub 下载本仓库的 skills 目录，并安装到用户的 Coding Agent 平台中。

## 目标安装路径

根据用户使用的平台，选择对应的目标路径：
- **Claude Code**: `~/.claude/skills`
- **OpenCode**: `~/.config/opencode/skill`
- **Codex**: `$CODEX_HOME/skills`（macOS/Linux 默认：`~/.codex/skills`）

## 安装步骤

**重要提示**：请使用 Bash 工具**批量执行**以下命令，一次性完成下载和安装，避免逐个文件操作。

### 第 1 步：确定仓库 URL

如果用户提供了本文档的 GitHub 网页链接（如 `https://github.com/username/repo/blob/main/skill-install-guide.md`），提取出仓库地址：`https://github.com/username/repo`

### 第 2 步：下载并安装（根据平台选择）

使用以下**完整命令序列**，一次性完成所有操作：

#### 安装到 Claude Code
```bash
REPO_URL="https://github.com/username/repo"  # 替换为实际仓库地址
cd /tmp && \
git clone --depth 1 "$REPO_URL" temp-skills-install && \
mkdir -p ~/.claude/skills && \
cp -r temp-skills-install/skills/* ~/.claude/skills/ && \
rm -rf temp-skills-install && \
echo "安装完成！验证：" && ls -la ~/.claude/skills/
```

#### 安装到 OpenCode
```bash
REPO_URL="https://github.com/username/repo"  # 替换为实际仓库地址
cd /tmp && \
git clone --depth 1 "$REPO_URL" temp-skills-install && \
mkdir -p ~/.config/opencode/skill && \
cp -r temp-skills-install/skills/* ~/.config/opencode/skill/ && \
rm -rf temp-skills-install && \
echo "安装完成！验证：" && ls -la ~/.config/opencode/skill/
```

#### 安装到 Codex
```bash
REPO_URL="https://github.com/username/repo"  # 替换为实际仓库地址
cd /tmp && \
git clone --depth 1 "$REPO_URL" temp-skills-install && \
mkdir -p ~/.codex/skills && \
cp -r temp-skills-install/skills/* ~/.codex/skills/ && \
rm -rf temp-skills-install && \
echo "安装完成！验证：" && ls -la ~/.codex/skills/
```

## 命令说明

- `REPO_URL="..."`: 设置仓库地址变量，根据文档 URL 提取
- `git clone --depth 1`: 浅克隆，只下载最新版本，加快速度
- `mkdir -p`: 自动创建目标目录（包括父目录）
- `cp -r`: 递归复制整个 skills 目录（包括所有文件和子目录）
- `rm -rf`: 清理临时目录
- `&&`: 确保命令顺序执行，前一步成功才继续

## 执行要求

1. **一次性执行完整命令序列**，不要分步操作
2. 根据用户提供的文档 URL，提取并替换 `REPO_URL` 变量
3. 根据用户使用的平台，选择对应的命令序列
4. 执行完成后，命令会自动验证安装结果
