# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import json
import urllib.parse
from typing import List, Dict, Optional, Any
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

_COUNTRIES_CACHE: List[Dict[str, Any]] = []


async def _load_countries() -> List[Dict[str, Any]]:
    global _COUNTRIES_CACHE
    if _COUNTRIES_CACHE:
        return _COUNTRIES_CACHE

    url = "https://cdn.jsdelivr.net/gh/mledoze/countries@master/countries.json"
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.get(url)
        if res.status_code == 200:
            _COUNTRIES_CACHE = res.json()
            return _COUNTRIES_CACHE
    return []


@Friday.register_on_cmd(
    ["country", "nation", "callcode"],
    cmd_help={
        "help": "Lookup country information by country name, calling code (e.g. +91, +1, +44), or ISO code.",
        "example": "country Japan or country +91 or country US",
    },
    requires_input=True,
)
async def country_info(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    query = m.user_input.strip()
    msg = await m.handle_message(f"🌍 Looking up country <b>{query}</b>...")

    try:
        countries = await _load_countries()
        if not countries:
            return await msg.edit_msg("❌ Failed to load country dataset.")

        match = None
        clean_q = query.lower()

        # Check by calling code (+91, 91, +1)
        if clean_q.startswith("+") or clean_q.isdigit():
            target_code = clean_q.lstrip("+")
            for item in countries:
                idd = item.get("idd", {})
                root = idd.get("root", "").lstrip("+")
                suffixes = idd.get("suffixes", [""])
                for s in suffixes:
                    full_code = f"{root}{s}"
                    if full_code == target_code or root == target_code:
                        match = item
                        break
                if match:
                    break

        # Check by ISO code or Name
        if not match:
            for item in countries:
                common_name = item.get("name", {}).get("common", "").lower()
                official_name = item.get("name", {}).get("official", "").lower()
                cca2 = item.get("cca2", "").lower()
                cca3 = item.get("cca3", "").lower()

                if clean_q in (common_name, official_name, cca2, cca3):
                    match = item
                    break

        # Partial matching fallback
        if not match:
            for item in countries:
                if clean_q in item.get("name", {}).get("common", "").lower():
                    match = item
                    break

        if not match:
            return await msg.edit_msg(f"❌ No country found matching <code>{query}</code>.")

        common_name = match.get("name", {}).get("common", query.title())
        official_name = match.get("name", {}).get("official", common_name)
        flag = match.get("flag", "🏳️")
        capital_list = match.get("capital", [])
        capital = ", ".join(capital_list) if capital_list else "None"
        region = match.get("region", "N/A")
        subregion = match.get("subregion", "N/A")

        # Calling code
        idd = match.get("idd", {})
        root = idd.get("root", "")
        suffixes = idd.get("suffixes", [])
        call_code = f"{root}{suffixes[0]}" if (root and suffixes) else (root or "N/A")

        # Currencies
        currencies = match.get("currencies", {})
        curr_str = ", ".join([f"{v.get('name', k)} ({v.get('symbol', k)})" for k, v in currencies.items()]) or "N/A"

        # Languages
        languages = match.get("languages", {})
        lang_str = ", ".join(languages.values()) or "N/A"

        area = f"{match.get('area', 0):,} km²"
        cca2 = match.get("cca2", "N/A")
        cca3 = match.get("cca3", "N/A")

        gmaps = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(common_name)}"

        report = (
            f"<b>{flag} {common_name} ({cca2}/{cca3})</b>\n"
            f"<i>{official_name}</i>\n\n"
            f"<b>• Capital:</b> {capital}\n"
            f"<b>• Calling Code:</b> <code>{call_code}</code>\n"
            f"<b>• Region:</b> {region} ({subregion})\n"
            f"<b>• Currencies:</b> {curr_str}\n"
            f"<b>• Languages:</b> {lang_str}\n"
            f"<b>• Area:</b> {area}\n\n"
            f"🔗 <a href='{gmaps}'>View on Google Maps</a>"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ Country lookup error: <code>{e}</code>")
