# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import socket
import datetime
from typing import Optional, Dict, Any
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


async def _fetch_ip_intel(target: str) -> Optional[Dict[str, Any]]:
    """Fetch deep geolocation and ASN data from ip-api with full fields."""
    fields = "status,message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,offset,currency,isp,org,as,asname,reverse,mobile,proxy,hosting,query"
    url = f"http://ip-api.com/json/{target}?fields={fields}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(url)
        if res.status_code == 200:
            data = res.json()
            if data.get("status") == "success":
                return data
    return None


@Friday.register_on_cmd(
    ["ip", "iplookup", "geoip", "whoisip"],
    cmd_help={
        "help": "Lookup deep geolocation, ASN, ISP, VPN/Proxy status, and network intelligence for any IP or domain.",
        "example": "ip 1.1.1.1\nip github.com\nip 8.8.8.8",
    },
    requires_input=True,
)
async def ip_lookup(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for IP lookup.")

    query = m.user_input.strip()
    # Strip protocol if user pasted URL
    if "://" in query:
        query = query.split("://")[1].split("/")[0].split(":")[0]

    msg = await m.handle_message(f"🌐 Querying intelligence for <code>{query}</code>...")

    try:
        data = await _fetch_ip_intel(query)
        if not data:
            return await msg.edit_msg(f"❌ Failed to locate information for <code>{query}</code>.")

        ip_addr = data.get("query", query)
        country = data.get("country", "Unknown")
        country_code = data.get("countryCode", "")
        region = data.get("regionName", "")
        city = data.get("city", "")
        postal = data.get("zip", "N/A")
        lat = data.get("lat", 0.0)
        lon = data.get("lon", 0.0)
        isp = data.get("isp", "N/A")
        org = data.get("org", "N/A")
        as_info = data.get("as", "N/A")
        rdns = data.get("reverse", "N/A")
        tz = data.get("timezone", "UTC")
        currency = data.get("currency", "N/A")
        is_proxy = "🛡️ Yes (VPN/Proxy/Tor)" if data.get("proxy") else "✅ No (Residential/Clean)"
        is_hosting = "🏢 Yes (Data Center/Cloud)" if data.get("hosting") else "🏠 Residential"
        is_mobile = "📱 Cellular Mobile" if data.get("mobile") else "💻 Fixed Line / Broadband"

        gmaps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

        report = (
            f"🌐 <b>IP Geolocation & Network Intelligence</b>\n\n"
            f"• <b>Target:</b> <code>{ip_addr}</code>\n"
            f"• <b>Reverse DNS:</b> <code>{rdns}</code>\n\n"
            f"📍 <b>Location Details:</b>\n"
            f"  - <b>Country:</b> {country} ({country_code})\n"
            f"  - <b>City / Region:</b> {city}, {region}\n"
            f"  - <b>Postal Code:</b> <code>{postal}</code>\n"
            f"  - <b>Coordinates:</b> <code>{lat}, {lon}</code> (<a href='{gmaps_url}'>Maps</a>)\n"
            f"  - <b>Timezone:</b> <code>{tz}</code>\n"
            f"  - <b>Currency:</b> <code>{currency}</code>\n\n"
            f"🏢 <b>Autonomous System & ISP:</b>\n"
            f"  - <b>ISP:</b> {isp}\n"
            f"  - <b>Organization:</b> {org}\n"
            f"  - <b>ASN:</b> <code>{as_info}</code>\n\n"
            f"🛡️ <b>Threat & Connection Profile:</b>\n"
            f"  - <b>Proxy/VPN Detection:</b> {is_proxy}\n"
            f"  - <b>Host Type:</b> {is_hosting}\n"
            f"  - <b>Connection:</b> {is_mobile}"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ IP Lookup error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["myip", "ipme"],
    cmd_help={
        "help": "Display current public IP address and host network location.",
        "example": "myip",
    },
)
async def my_ip(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    msg = await m.handle_message("🌐 Fetching host public IP...")
    try:
        data = await _fetch_ip_intel("")
        if not data:
            return await msg.edit_msg("❌ Could not determine host public IP.")

        ip_addr = data.get("query")
        isp = data.get("isp")
        city = data.get("city")
        country = data.get("country")

        report = (
            f"🖥️ <b>Host Public IP:</b> <code>{ip_addr}</code>\n"
            f"• <b>ISP:</b> {isp}\n"
            f"• <b>Location:</b> {city}, {country}\n\n"
            "<i>(Ensure this is kept private if operating on personal residential network)</i>"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ Error: <code>{e}</code>")
