#!/usr/bin/env python3
"""
Telegram-agents heartbeat dispatcher: read agents.yaml, match cron expressions,
send heartbeat messages as the user via Telethon (User API).
Called by launchd every minute via: cat dispatcher.py | python3
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from telethon import TelegramClient
    import python_socks
except ImportError:
    print("ERROR: telethon/python-socks not installed. Run: pip3 install telethon 'python-socks[asyncio]'", file=sys.stderr)
    sys.exit(1)

# --- Config ---

CHANNELS_DIR = os.path.expanduser("~/.claude/channels")
CONFIG_DIR = os.path.expanduser("~/.config/telegram-agents")
CONFIG_FILE = os.path.join(CONFIG_DIR, "agents.yaml")
SESSION_PATH = os.path.join(CONFIG_DIR, "user")

# Official TelegramDesktop credentials
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

# --- Logging ---

logging.basicConfig(
    filename="/tmp/telegram-agents.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# --- Cron expression matching (ported from clean-cron/scripts/dispatch.py) ---


def _field_match(pattern, value, max_val):
    """Match a single cron field against a value."""
    if pattern == "*":
        return True
    for part in pattern.split(","):
        if "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            if base == "*":
                if value % step == 0:
                    return True
            elif "-" in base:
                lo, hi = map(int, base.split("-", 1))
                if lo <= value <= hi and (value - lo) % step == 0:
                    return True
        elif "-" in part:
            lo, hi = map(int, part.split("-", 1))
            if lo <= value <= hi:
                return True
        else:
            if int(part) == value:
                return True
    return False


def cron_match(expr, now):
    """Match a 5-field cron expression against a datetime."""
    fields = expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    # cron: 0=Sunday, python: 0=Monday → convert
    py_dow = now.isoweekday() % 7  # Mon=1..Sun=0 in cron convention
    return (
        _field_match(minute, now.minute, 59)
        and _field_match(hour, now.hour, 23)
        and _field_match(dom, now.day, 31)
        and _field_match(month, now.month, 12)
        and _field_match(dow, py_dow, 7)
    )


# --- Proxy ---


def detect_proxy():
    """Detect proxy from environment variables."""
    proxy_url = os.environ.get("all_proxy") or os.environ.get("http_proxy") or ""
    if not proxy_url:
        return None
    m = re.match(r"(socks5|http)://([^:]+):(\d+)", proxy_url)
    if not m:
        return None
    scheme, host, port = m.group(1), m.group(2), int(m.group(3))
    proxy_type = python_socks.ProxyType.SOCKS5 if scheme == "socks5" else python_socks.ProxyType.HTTP
    return (proxy_type, host, port)


# --- Telegram ---


def get_bot_username(state_dir):
    """Get bot @username by calling Bot API getMe with the bot's token."""
    env_path = os.path.join(CHANNELS_DIR, state_dir, ".env")
    if not os.path.exists(env_path):
        raise FileNotFoundError(f".env not found: {env_path}")
    token = None
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
    if not token:
        raise ValueError(f"TELEGRAM_BOT_TOKEN not found in {env_path}")

    import urllib.request
    url = f"https://api.telegram.org/bot{token}/getMe"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.load(resp)
    return "@" + data["result"]["username"]


async def send_heartbeats(pending):
    """Send all pending heartbeat messages as the user via Telethon."""
    if not os.path.exists(SESSION_PATH + ".session"):
        log.error("Session file not found: %s.session — run auth.py first", SESSION_PATH)
        return

    proxy = detect_proxy()
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH, proxy=proxy)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            log.error("Session not authorized — run auth.py to re-authenticate")
            return

        for agent_name, bot_username, message in pending:
            try:
                await client.send_message(bot_username, message)
                log.info("Sent heartbeat for agent=%s", agent_name)
            except Exception as e:
                log.error("Failed to send to agent=%s: %s", agent_name, e)
    finally:
        await client.disconnect()


# --- Main ---


def main():
    if not os.path.exists(CONFIG_FILE):
        return

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    if not config or "agents" not in config:
        return

    now = datetime.now()
    pending = []

    for agent_name, agent_cfg in config["agents"].items():
        state_dir = agent_cfg.get("state_dir")
        heartbeats = agent_cfg.get("heartbeats", [])

        if not state_dir or not heartbeats:
            continue

        for hb in heartbeats:
            schedule = hb.get("schedule", "")
            prompt = hb.get("prompt", "")
            if not schedule or not prompt:
                continue

            if cron_match(schedule, now):
                try:
                    bot_username = get_bot_username(state_dir)
                    timestamp = now.strftime("%Y-%m-%d %H:%M")
                    message = f"[定时任务 {timestamp}] {prompt}"
                    pending.append((agent_name, bot_username, message))
                except (FileNotFoundError, ValueError) as e:
                    log.warning("Config error for agent=%s: %s", agent_name, e)

    if pending:
        asyncio.run(send_heartbeats(pending))


if __name__ == "__main__":
    main()
