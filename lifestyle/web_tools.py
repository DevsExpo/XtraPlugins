# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import urllib.parse
from typing import Optional
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _clean_url(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


@Friday.register_on_cmd(
    ["webshot", "ss"],
    cmd_help={
        "help": "Capture a full-browser screenshot of a given webpage URL.",
        "example": "webshot https://github.com/FridaySoftware",
    },
    requires_input=True,
)
async def web_screenshot(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for webshot.")

    target_url = _clean_url(m.user_input)
    msg = await m.handle_message(f"📸 Capturing screenshot of <code>{target_url}</code>...")

    encoded = urllib.parse.quote_plus(target_url)
    screenshot_api = f"https://image.thum.io/get/width/1280/crop/800/noanimate/{target_url}"

    os.makedirs("temp/xtra_web", exist_ok=True)
    out_file = f"temp/xtra_web/webshot_{m.id}.png"

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await client.get(screenshot_api, follow_redirects=True)

        if res.status_code != 200 or len(res.content) < 1000:
            # Fallback to secondary screenshot provider
            alt_api = f"https://mini.s-shot.ru/1024x768/PNG/1024/Z100/?{target_url}"
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.get(alt_api, follow_redirects=True)

        if res.status_code != 200 or len(res.content) < 1000:
            return await msg.edit_msg("❌ Failed to capture screenshot. The webpage may be blocked or unreachable.")

        with open(out_file, "wb") as f:
            f.write(res.content)

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_file,
            caption=f"📸 <b>Webshot:</b> <code>{target_url}</code>",
            reply_to=m.id,
        )
        try:

            await msg.delete()

        except Exception:

            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Screenshot error: <code>{e}</code>")
    finally:
        if os.path.exists(out_file):
            try:
                os.remove(out_file)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["dns", "nslookup"],
    cmd_help={
        "help": "Resolve DNS records (A, AAAA, MX, TXT, CNAME, NS) via Cloudflare DoH.",
        "example": "dns google.com or dns telegram.org MX",
    },
    requires_input=True,
)
async def dns_lookup(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    parts = m.user_input.strip().split()
    domain = parts[0].replace("https://", "").replace("http://", "").split("/")[0]
    record_type = parts[1].upper() if len(parts) > 1 else "A"

    msg = await m.handle_message(f"🌐 Querying <b>{record_type}</b> records for <code>{domain}</code>...")

    url = f"https://cloudflare-dns.com/dns-query?name={domain}&type={record_type}"
    headers = {"accept": "application/dns-json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)

        if res.status_code != 200:
            return await msg.edit_msg(f"❌ DNS query failed with HTTP {res.status_code}.")

        data = res.json()
        answers = data.get("Answer", [])

        if not answers:
            return await msg.edit_msg(f"ℹ️ No <b>{record_type}</b> records found for <code>{domain}</code>.")

        entries = []
        for ans in answers:
            entries.append(f"• <code>{ans.get('data')}</code> (TTL: {ans.get('TTL')}s)")

        report = (
            f"🌐 <b>DNS Records ({record_type}):</b> <code>{domain}</code>\n\n"
            + "\n".join(entries)
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ DNS query error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["whois"],
    cmd_help={
        "help": "Perform RDAP / WHOIS domain registration lookup.",
        "example": "whois github.com",
    },
    requires_input=True,
)
async def whois_lookup(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    domain = m.user_input.strip().replace("https://", "").replace("http://", "").split("/")[0]
    msg = await m.handle_message(f"🔍 Looking up WHOIS / RDAP for <code>{domain}</code>...")

    url = f"https://rdap.org/domain/{domain}"

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            res = await client.get(url)

        if res.status_code != 200:
            return await msg.edit_msg(f"❌ WHOIS lookup failed (HTTP {res.status_code}).")

        data = res.json()
        handle = data.get("handle", domain)
        status = ", ".join(data.get("status", ["active"]))

        # Extract events (creation, expiration)
        events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", [])}
        created = events.get("registration", "Unknown")[:10]
        expires = events.get("expiration", "Unknown")[:10]
        changed = events.get("last changed", "Unknown")[:10]

        # Nameservers
        ns_list = [ns.get("ldhName") for ns in data.get("nameservers", []) if ns.get("ldhName")]
        ns_str = ", ".join(ns_list[:4]) if ns_list else "Unknown"

        report = (
            f"🔍 <b>WHOIS / RDAP Record:</b> <code>{domain}</code>\n\n"
            f"<b>• Handle:</b> <code>{handle}</code>\n"
            f"<b>• Registered:</b> <code>{created}</code>\n"
            f"<b>• Expires:</b> <code>{expires}</code>\n"
            f"<b>• Last Updated:</b> <code>{changed}</code>\n"
            f"<b>• Nameservers:</b> <code>{ns_str}</code>\n"
            f"<b>• Status:</b> <code>{status}</code>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ WHOIS error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["iplookup", "ip"],
    cmd_help={
        "help": "Get geolocation and ISP info of an IP address or domain.",
        "example": "ip 1.1.1.1 or ip telegram.org",
    },
    requires_input=True,
)
async def ip_lookup(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    target = m.user_input.strip().replace("https://", "").replace("http://", "").split("/")[0]
    msg = await m.handle_message(f"📍 Geocoding IP <code>{target}</code>...")

    url = f"http://ip-api.com/json/{target}?fields=status,message,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url)

        if res.status_code != 200:
            return await msg.edit_msg(f"❌ IP lookup failed with HTTP {res.status_code}.")

        data = res.json()
        if data.get("status") != "success":
            return await msg.edit_msg(f"❌ Failed: <i>{data.get('message', 'Unknown host')}</i>")

        ip = data.get("query")
        country = data.get("country")
        region = data.get("regionName")
        city = data.get("city")
        isp = data.get("isp")
        asn = data.get("as")
        tz = data.get("timezone")
        coords = f"{data.get('lat')}, {data.get('lon')}"

        report = (
            f"📍 <b>IP Geolocation:</b> <code>{ip}</code>\n\n"
            f"<b>• Country:</b> {country}\n"
            f"<b>• Region / City:</b> {city}, {region}\n"
            f"<b>• ISP:</b> <code>{isp}</code>\n"
            f"<b>• ASN:</b> <code>{asn}</code>\n"
            f"<b>• Timezone:</b> <code>{tz}</code>\n"
            f"<b>• Coordinates:</b> <code>{coords}</code>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ IP lookup error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["unshorten", "unshort"],
    cmd_help={
        "help": "Follow redirects and unshorten shortened links (bit.ly, t.co, etc.).",
        "example": "unshorten https://bit.ly/example",
    },
    requires_input=True,
)
async def unshorten_link(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    target_url = _clean_url(m.user_input)
    msg = await m.handle_message("🔗 Resolving redirect trail...")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.head(target_url)

        final_url = str(res.url)
        report = (
            "🔗 <b>Link Unshortened:</b>\n\n"
            f"<b>• Original:</b> <code>{target_url}</code>\n"
            f"<b>• Destination:</b> <code>{final_url}</code>\n"
            f"<b>• Status Code:</b> <code>{res.status_code}</code>"
        )
        await msg.edit_msg(report, disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_msg(f"❌ Error unshortening link: <code>{e}</code>")
