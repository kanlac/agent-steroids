import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFileSync } from "fs";
import { join } from "path";

function loadEnv(): { token: string; defaultChatId?: string } {
  let token = process.env.TELEGRAM_BOT_TOKEN || "";
  let defaultChatId = process.env.TELEGRAM_CHAT_ID || "";
  if (!token) {
    try {
      const envPath = join(
        process.env.HOME || "~",
        ".claude/channels/telegram/.env"
      );
      const content = readFileSync(envPath, "utf-8");
      const tokenMatch = content.match(/TELEGRAM_BOT_TOKEN=(.+)/);
      if (tokenMatch) token = tokenMatch[1].trim();
      if (!defaultChatId) {
        const chatMatch = content.match(/TELEGRAM_CHAT_ID=(.+)/);
        if (chatMatch) defaultChatId = chatMatch[1].trim();
      }
    } catch {}
  }
  if (!token) throw new Error("TELEGRAM_BOT_TOKEN not found");
  return { token, defaultChatId: defaultChatId || undefined };
}

const { token: TOKEN, defaultChatId: DEFAULT_CHAT_ID } = loadEnv();
const API = `https://api.telegram.org/bot${TOKEN}`;

const server = new McpServer({ name: "telegram-notify", version: "1.0.0" });

server.tool(
  "telegram_notify",
  "Send a text message to a Telegram chat. Use for notifications and status updates.",
  {
    chat_id: z.string().optional().describe("Telegram chat ID (uses default if omitted)"),
    text: z.string().describe("Message text (Markdown supported)"),
  },
  async ({ chat_id, text }) => {
    chat_id = chat_id || DEFAULT_CHAT_ID;
    if (!chat_id)
      return { content: [{ type: "text", text: "Error: no chat_id provided and no default configured" }] };
    const res = await fetch(`${API}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id, text, parse_mode: "Markdown" }),
    });
    const data = await res.json();
    if (!data.ok)
      return { content: [{ type: "text", text: `Error: ${data.description}` }] };
    return {
      content: [{ type: "text", text: `Sent to ${chat_id} (msg ${data.result.message_id})` }],
    };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
