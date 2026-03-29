#!/bin/bash
# 一键复现脚本：验证 Bun 新版本是否修复 proxy + ReadableStream body bug
# 前提：HTTP 代理运行中，bot token 配置在 ~/.claude/channels/telegram/.env
# 用法：bash scripts/test-bun-proxy-stream.sh <chat_id>
#
# 退出码：
#   0 = FIXED（可移除 undici patch）
#   1 = STILL BROKEN（继续保留 patch）
#   2 = 其他错误

CHAT_ID="${1:?用法: $0 <chat_id>}"
PLUGIN_DIR="$HOME/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram"

if [ ! -d "$PLUGIN_DIR" ]; then
  echo "ERROR: Telegram plugin 目录不存在: $PLUGIN_DIR"
  exit 2
fi

SCRIPT=$(cat <<EOF
import { Bot, InputFile } from "grammy";
import { readFileSync, writeFileSync } from "fs";

const TOKEN = readFileSync(
  \`\${process.env.HOME}/.claude/channels/telegram/.env\`, "utf8"
).match(/TELEGRAM_BOT_TOKEN=(.+)/)?.[1]?.trim();
const CHAT_ID = "${CHAT_ID}";

writeFileSync("/tmp/bun-proxy-test.txt", "Bun proxy streaming body test " + new Date().toISOString());

const bot = new Bot(TOKEN!);
try {
  const r = await bot.api.sendDocument(CHAT_ID, new InputFile("/tmp/bun-proxy-test.txt"));
  console.log("FIXED: Bun " + Bun.version + " proxy + ReadableStream body works! message_id:", r.message_id);
  console.log("可以移除 undici patch。");
  process.exit(0);
} catch (err: any) {
  if (err?.message?.includes("socket connection was closed")) {
    console.log("STILL BROKEN: Bun " + Bun.version + " — 继续保留 undici patch。");
    process.exit(1);
  }
  console.error("Unexpected error:", err?.message);
  process.exit(2);
}
EOF
)

echo "$SCRIPT" > /tmp/test-bun-proxy-stream.ts
cd "$PLUGIN_DIR" && bun run /tmp/test-bun-proxy-stream.ts
