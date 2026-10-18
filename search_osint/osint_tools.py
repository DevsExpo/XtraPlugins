# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import re
import asyncio
from typing import Tuple
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

PLATFORMS = [
    ("GitHub", "https://github.com/{}", 200),
    ("Telegram", "https://t.me/{}", 200),
    ("Reddit", "https://www.reddit.com/user/{}", 200),
    ("Twitter/X", "https://twitter.com/{}", 200),
    ("Instagram", "https://www.instagram.com/{}/", 200),
    ("Pinterest", "https://www.pinterest.com/{}/", 200),
    ("TikTok", "https://www.tiktok.com/@{}", 200),
    ("Steam", "https://steamcommunity.com/id/{}", 200),
    ("GitLab", "https://gitlab.com/{}", 200),
]


async def _probe_platform(client: httpx.AsyncClient, name: str, url_fmt: str, username: str) -> Tuple[str, str, bool]:
    url = url_fmt.format(username)
    try:
        res = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True)
        # Check standard positive status codes
        if res.status_code == 200 and "not found" not in res.text.lower() and "404" not in res.text.lower():
            return name, url, True
    except Exception:
        pass
    return name, url, False


@Friday.register_on_cmd(
    ["osint", "sherlock", "stalk"],
    cmd_help={
        "help": "Scan 10+ major social platforms concurrently to locate profiles for a given username.",
        "example": "osint torvalds",
    },
    requires_input=True,
)
async def osint_username_lookup(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    username = m.user_input.strip().lstrip("@")
    msg = await m.handle_message(f"🕵️ Scanning social networks for <code>@{username}</code>...")

    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [_probe_platform(client, name, url, username) for name, url, _ in PLATFORMS]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    found_links = []
    for item in outcomes:
        if isinstance(item, tuple) and item[2]:
            found_links.append(f"• <b>{item[0]}:</b> <a href='{item[1]}'>Profile Link</a>")

    if not found_links:
        return await msg.edit_msg(f"🤷‍♂️ No public profiles confirmed for <code>@{username}</code>.")

    report = (
        f"🕵️ <b>OSINT Reconnaissance:</b> <code>@{username}</code>\n\n"
        f"<b>Confirmed Profiles ({len(found_links)}):</b>\n" + "\n".join(found_links)
    )
    await msg.edit_msg(report, disable_web_page_preview=True)


@Friday.register_on_cmd(
    ["subdomains", "subdomain"],
    cmd_help={
        "help": "Enumerate discovered subdomains for a domain using certificate transparency logs.",
        "example": "subdomains telegram.org",
    },
    requires_input=True,
)
async def subdomains_lookup(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    domain = m.user_input.strip().replace("https://", "").replace("http://", "").split("/")[0]
    msg = await m.handle_message(f"🌐 Querying certificate logs for <code>{domain}</code>...")

    url = f"https://crt.sh/?q=%.{domain}&output=json"

    try:
        async with httpx.AsyncClient(timeout=18.0) as client:
            res = await client.get(url, headers={"User-Agent": "FridayUserbot/1.0"})

        if res.status_code != 200:
            return await msg.edit_msg(f"❌ Certificate transparency service returned HTTP {res.status_code}.")

        data = res.json()
        subdomains = set()
        for item in data:
            name_value = item.get("name_value", "")
            for sub in name_value.split("\n"):
                sub_clean = sub.strip().lower()
                if sub_clean.endswith(domain) and not sub_clean.startswith("*"):
                    subdomains.add(sub_clean)

        if not subdomains:
            return await msg.edit_msg(f"ℹ️ No subdomains indexed for <code>{domain}</code>.")

        sorted_subs = sorted(list(subdomains))
        count = len(sorted_subs)
        display = sorted_subs[:30]

        lines = [f"• <code>{s}</code>" for s in display]
        body = "\n".join(lines)
        if count > 30:
            body += f"\n<i>...and {count - 30} more subdomains</i>"

        report = f"🌐 <b>Subdomain Enumeration ({count}):</b> <code>{domain}</code>\n\n{body}"
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Subdomain query error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["emailcheck", "checkemail"],
    cmd_help={
        "help": "Validate email format and check for disposable temporary email domains.",
        "example": "emailcheck user@tempmail.com",
    },
    requires_input=True,
)
async def check_email_osint(c: Client, m: Message):
    email = m.user_input.strip()
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

    if not re.match(pattern, email):
        return await m.handle_message(f"❌ <code>{email}</code> is not a valid email syntax.")

    domain = email.split("@")[1].lower()
    disposable_domains = {
        "10minutemail.com",
        "guerrillamail.com",
        "tempmail.com",
        "throwawaymail.com",
        "mailinator.com",
        "yopmail.com",
        "trashmail.com",
        "getairmail.com",
        "dispostable.com",
    }

    is_disposable = "⚠️ Yes (Disposable / Burner)" if domain in disposable_domains else "✅ Clean (Legitimate Domain)"
    report = (
        f"📧 <b>Email Inspection:</b> <code>{email}</code>\n\n"
        f"<b>• Domain:</b> <code>{domain}</code>\n"
        f"<b>• Format:</b> Valid\n"
        f"<b>• Disposable Check:</b> {is_disposable}"
    )
    await m.handle_message(report)
