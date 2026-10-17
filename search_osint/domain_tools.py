# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import httpx
import html
from typing import Dict, List, Any

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message


@Friday.register_on_cmd(
    ["dns", "dnslookup"],
    cmd_help={
        "help": "Query authoritative DNS records (A, AAAA, MX, TXT, NS, CNAME) via Cloudflare DoH.",
        "example": "dns google.com\ndns github.com",
    },
    requires_input=True,
)
async def dns_lookup_cmd(c: Client, m: Message):
    domain = m.user_input.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        domain = domain.split("//")[1].split("/")[0]

    msg = await m.handle_message(f"🌐 Querying DNS records for <code>{domain}</code>...")
    record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]
    results: Dict[str, List[str]] = {}

    headers = {"Accept": "application/dns-json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for r_type in record_types:
            try:
                resp = await client.get(
                    "https://cloudflare-dns.com/dns-query",
                    params={"name": domain, "type": r_type},
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    answers = data.get("Answer", [])
                    if answers:
                        results[r_type] = [ans.get("data") for ans in answers if ans.get("data")]
            except Exception:
                pass

    if not results:
        return await msg.edit_msg(f"❌ No DNS records found for <code>{domain}</code>.")

    blocks = []
    for r_type, records in results.items():
        recs_str = "\n".join(f"  • <code>{html.escape(r)}</code>" for r in records[:5])
        blocks.append(f"<b>[{r_type} Records]:</b>\n{recs_str}")

    report = (
        f"🌐 <b>DNS Records:</b> <code>{domain}</code>\n\n"
        + "\n\n".join(blocks)
    )
    await msg.edit_msg(report)


@Friday.register_on_cmd(
    ["whois", "domainwhois", "rdap"],
    cmd_help={
        "help": "Inspect domain registration, registrar, creation, and expiration dates via RDAP.",
        "example": "whois telegram.org\nwhois wikipedia.org",
    },
    requires_input=True,
)
async def whois_lookup_cmd(c: Client, m: Message):
    domain = m.user_input.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        domain = domain.split("//")[1].split("/")[0]

    msg = await m.handle_message(f"🔍 Fetching WHOIS / RDAP metadata for <code>{domain}</code>...")
    url = f"https://rdap.org/domain/{domain}"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return await msg.edit_msg(f"❌ Could not retrieve WHOIS data for <code>{domain}</code> (HTTP {resp.status_code}).")
            data = resp.json()

        handle = data.get("handle") or domain.upper()
        status_list = data.get("status", [])
        status_str = ", ".join(status_list[:3]) if status_list else "Active"

        events = {ev.get("eventAction"): ev.get("eventDate", "")[:10] for ev in data.get("events", [])}
        created = events.get("registration") or "Unknown"
        expired = events.get("expiration") or "Unknown"
        updated = events.get("last changed") or "Unknown"

        nameservers = [ns.get("ldhName") for ns in data.get("nameservers", []) if ns.get("ldhName")]
        ns_str = ", ".join(nameservers[:4]) if nameservers else "Unknown"

        # Registrar entities
        registrar = "Unknown"
        for ent in data.get("entities", []):
            roles = ent.get("roles", [])
            if "registrar" in roles:
                vcard = ent.get("vcardArray", [])
                if len(vcard) > 1:
                    for prop in vcard[1]:
                        if prop[0] == "fn":
                            registrar = prop[3]
                            break

        report = (
            f"📋 <b>WHOIS Domain Report:</b> <code>{domain}</code>\n\n"
            f"🏢 <b>Registrar:</b> <code>{registrar}</code>\n"
            f"🆔 <b>Domain Handle:</b> <code>{handle}</code>\n"
            f"📅 <b>Registered On:</b> <code>{created}</code>\n"
            f"⏳ <b>Expires On:</b> <code>{expired}</code>\n"
            f"🔄 <b>Last Modified:</b> <code>{updated}</code>\n"
            f"⚡ <b>Status:</b> <code>{status_str}</code>\n"
            f"🌐 <b>Nameservers:</b> <code>{ns_str}</code>"
        )

        await msg.edit_msg(report)

    except Exception as e:
        await msg.edit_msg(f"❌ WHOIS error: <code>{e}</code>")
