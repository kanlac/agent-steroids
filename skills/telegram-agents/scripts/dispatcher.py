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
import subprocess
import sys
import time
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

# telethon and python_socks are imported lazily in send_heartbeats()
# so the dispatcher can still run (and skip heartbeats) without them installed

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
    import python_socks
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
    """Send all pending heartbeat messages as the user via Telethon.

    Each heartbeat entry includes an optional session name. Heartbeats are
    grouped by session so we only open one TelegramClient per unique session.
    """
    try:
        from telethon import TelegramClient
    except ImportError:
        log.error("telethon not installed — run: pip3 install telethon 'python-socks[asyncio]'")
        return

    proxy = detect_proxy()

    # Group by session path
    by_session = {}
    for agent_name, bot_username, message, session_name in pending:
        session_path = os.path.join(CONFIG_DIR, session_name) if session_name else SESSION_PATH
        by_session.setdefault(session_path, []).append((agent_name, bot_username, message))

    for session_path, items in by_session.items():
        if not os.path.exists(session_path + ".session"):
            agent_names = ", ".join(a for a, _, _ in items)
            log.error("Session file not found: %s.session (agents: %s) — run: python3 auth.py %s",
                       session_path, agent_names, os.path.basename(session_path))
            continue

        client = TelegramClient(session_path, API_ID, API_HASH, proxy=proxy)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                log.error("Session not authorized: %s — run: python3 auth.py %s",
                           session_path, os.path.basename(session_path))
                continue

            for agent_name, bot_username, message in items:
                try:
                    await client.send_message(bot_username, message)
                    log.info("Sent heartbeat for agent=%s via session=%s", agent_name, os.path.basename(session_path))
                except Exception as e:
                    log.error("Failed to send to agent=%s: %s", agent_name, e)
        finally:
            await client.disconnect()


# --- Restart ---


def restart_agents(config):
    """Restart all agent tmux windows to pick up plugin/skill updates."""
    tmux_session = config.get("tmux_session", "channels")
    agents = config.get("agents", {})

    # Check if tmux session exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", tmux_session], capture_output=True
    )
    if result.returncode != 0:
        log.info("tmux session '%s' not found, skipping restart", tmux_session)
        return

    for agent_name, agent_cfg in agents.items():
        state_dir = agent_cfg.get("state_dir", "telegram")
        agent_id = agent_cfg.get("agent", "")
        work_dir = os.path.expanduser(agent_cfg.get("dir", "~"))

        # Build claude command
        cmd_parts = []
        if state_dir != "telegram":
            cmd_parts.append(
                f"TELEGRAM_STATE_DIR=~/.claude/channels/{state_dir}"
            )
        cmd_parts.append("claude")
        cmd_parts.append("--channels 'plugin:telegram@claude-plugins-official'")
        if agent_id:
            cmd_parts.append(f"--agent {agent_id}")
        cmd_parts.append("--dangerously-skip-permissions")
        cmd_parts.append(
            """--settings '{"enabledPlugins":{"telegram@claude-plugins-official":true}}'"""
        )
        claude_cmd = " ".join(cmd_parts)

        # Kill existing window (ignore if not found)
        subprocess.run(
            ["tmux", "kill-window", "-t", f"{tmux_session}:{agent_name}"],
            capture_output=True,
        )
        time.sleep(1)

        # Check if session still exists (killed last window → session gone)
        result = subprocess.run(
            ["tmux", "has-session", "-t", tmux_session], capture_output=True
        )
        if result.returncode != 0:
            subprocess.run(
                [
                    "tmux", "new-session", "-d",
                    "-s", tmux_session,
                    "-n", agent_name,
                    "-c", work_dir,
                    claude_cmd,
                ],
                capture_output=True,
            )
        else:
            subprocess.run(
                [
                    "tmux", "new-window",
                    "-t", tmux_session,
                    "-n", agent_name,
                    "-c", work_dir,
                    claude_cmd,
                ],
                capture_output=True,
            )
        log.info("Restarted agent=%s", agent_name)

    log.info("All agents restarted for plugin reload")


# --- Main ---


def main():
    if not os.path.exists(CONFIG_FILE):
        return

    with open(CONFIG_FILE) as f:
        config = yaml.safe_load(f)

    if not config or "agents" not in config:
        return

    now = datetime.now()

    # Check restart schedule — restart takes priority over heartbeats
    restart_schedule = config.get("restart_schedule")
    if restart_schedule and cron_match(restart_schedule, now):
        log.info("Restart schedule matched: %s", restart_schedule)
        restart_agents(config)
        return

    pending = []

    for agent_name, agent_cfg in config["agents"].items():
        state_dir = agent_cfg.get("state_dir")
        heartbeats = agent_cfg.get("heartbeats", [])

        if not state_dir or not heartbeats:
            continue

        user_session = agent_cfg.get("user_session")  # per-agent session, or None for default

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
                    pending.append((agent_name, bot_username, message, user_session))
                except (FileNotFoundError, ValueError) as e:
                    log.warning("Config error for agent=%s: %s", agent_name, e)

    if pending:
        asyncio.run(send_heartbeats(pending))


if __name__ == "__main__":
    main()
