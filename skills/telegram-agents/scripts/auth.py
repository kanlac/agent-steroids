#!/usr/bin/env python3
"""
One-time Telethon authentication.
Creates a session file at ~/.config/telegram-agents/user.session
Run interactively: python3 auth.py

Auto-detects SOCKS5/HTTP proxy from environment variables (all_proxy, http_proxy).
"""

import asyncio
import os
import re

from telethon import TelegramClient
import python_socks

# Official TelegramDesktop credentials (public, safe for personal use)
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

SESSION_PATH = os.path.expanduser("~/.config/telegram-agents/user")


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
    print(f"Using proxy: {scheme}://{host}:{port}")
    return (proxy_type, host, port)


async def main():
    proxy = detect_proxy()
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH, proxy=proxy)
    await client.start()
    me = await client.get_me()
    print(f"Authenticated as: {me.first_name} (id: {me.id})")
    print(f"Session saved to: {SESSION_PATH}.session")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
