#!/usr/bin/env python3
"""
Telegram-agents heartbeat dispatcher: read agents.yaml, match cron expressions,
send heartbeat messages via Telegram Bot API for matching agents.
Called by launchd every minute via: cat dispatcher.py | python3
"""

import json
import logging
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

# --- YAML parsing ---
try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

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


# --- Telegram API ---

def read_bot_token(state_dir):
    """Read TELEGRAM_BOT_TOKEN from ~/.claude/channels/<state_dir>/.env"""
    env_path = os.path.expanduser(f"~/.claude/channels/{state_dir}/.env")
    if not os.path.exists(env_path):
        raise FileNotFoundError(f".env not found: {env_path}")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise ValueError(f"TELEGRAM_BOT_TOKEN not found in {env_path}")


def read_chat_id(state_dir):
    """Read chat_id from ~/.claude/channels/<state_dir>/access.json"""
    access_path = os.path.expanduser(f"~/.claude/channels/{state_dir}/access.json")
    if not os.path.exists(access_path):
        raise FileNotFoundError(f"access.json not found: {access_path}")
    with open(access_path) as f:
        data = json.load(f)
    allow_from = data.get("allowFrom", [])
    if not allow_from:
        raise ValueError(f"allowFrom is empty in {access_path}")
    return allow_from[0]


def send_telegram_message(bot_token, chat_id, text):
    """Send a message via Telegram Bot API using urllib.request."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


# --- Main ---

def main():
    config_file = os.path.expanduser("~/.config/telegram-agents/agents.yaml")
    if not os.path.exists(config_file):
        log.debug("Config not found: %s", config_file)
        return

    with open(config_file) as f:
        config = yaml.safe_load(f)

    if not config or "agents" not in config:
        log.debug("No agents defined in config")
        return

    now = datetime.now()

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

            if not cron_match(schedule, now):
                continue

            # Build timestamped message
            timestamp = now.strftime("%Y-%m-%d %H:%M")
            message = f"[定时任务 {timestamp}] {prompt}"

            try:
                bot_token = read_bot_token(state_dir)
                chat_id = read_chat_id(state_dir)
                send_telegram_message(bot_token, chat_id, message)
                log.info("Sent heartbeat for agent=%s schedule=%s prompt=%r", agent_name, schedule, prompt)
            except FileNotFoundError as e:
                log.warning("Config missing for agent=%s: %s", agent_name, e)
            except ValueError as e:
                log.warning("Config error for agent=%s: %s", agent_name, e)
            except urllib.error.URLError as e:
                log.error("Network error for agent=%s: %s", agent_name, e)
            except Exception as e:
                log.error("Unexpected error for agent=%s: %s", agent_name, e)


if __name__ == "__main__":
    main()
