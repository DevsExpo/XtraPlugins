# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import re
import urllib.parse
from bs4 import BeautifulSoup
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@Friday.register_on_cmd(
    ["ifsc"],
    cmd_help={
        "help": "Lookup Indian bank branch details by 11-digit IFSC code.",
        "example": "ifsc SBIN0000001 or ifsc HDFC0000001",
    },
    requires_input=True,
)
async def ifsc_lookup(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    code = m.user_input.strip().upper()
    if len(code) != 11:
        return await m.handle_message("❌ Invalid IFSC code. An IFSC code must be exactly 11 characters (e.g. <code>SBIN0000001</code>).")

    msg = await m.handle_message(f"🏦 Looking up IFSC <code>{code}</code>...")
    api_url = f"https://ifsc.razorpay.com/{code}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(api_url)

        if res.status_code == 404:
            return await msg.edit_msg(f"❌ IFSC Code <code>{code}</code> not found.")
        if res.status_code != 200:
            return await msg.edit_msg(f"❌ IFSC service error (HTTP {res.status_code}).")

        data = res.json()
        bank = data.get("BANK", "Unknown Bank")
        branch = data.get("BRANCH", "N/A")
        address = data.get("ADDRESS", "N/A")
        city = data.get("CITY", "N/A")
        district = data.get("DISTRICT", "N/A")
        state = data.get("STATE", "N/A")
        contact = data.get("CONTACT", "N/A")

        # Payment rails support
        upi = "✅" if data.get("UPI") else "❌"
        neft = "✅" if data.get("NEFT") else "❌"
        rtgs = "✅" if data.get("RTGS") else "❌"
        imps = "✅" if data.get("IMPS") else "❌"

        report = (
            f"🏦 <b>{bank}</b>\n"
            f"<b>• Branch:</b> <code>{branch}</code>\n"
            f"<b>• IFSC:</b> <code>{code}</code>\n"
            f"<b>• Address:</b> {address}\n"
            f"<b>• City/District:</b> {city}, {district}\n"
            f"<b>• State:</b> {state}\n"
            f"<b>• Contact:</b> <code>{contact}</code>\n\n"
            f"<b>Supported Payment Rails:</b>\n"
            f"UPI: {upi} | NEFT: {neft} | RTGS: {rtgs} | IMPS: {imps}"
        )
        await msg.edit_msg(report)
    except Exception as e:
        await msg.edit_msg(f"❌ IFSC lookup error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["bank", "bankifsc", "findifsc"],
    cmd_help={
        "help": "Find IFSC code by bank name and branch or city.",
        "example": "bank SBI Connaught Place New Delhi or bank HDFC Bandra Mumbai",
    },
    requires_input=True,
)
async def find_bank_ifsc(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    query = m.user_input.strip()
    msg = await m.handle_message(f"🔍 Searching IFSC code for <b>{query}</b>...")

    search_q = f"IFSC code {query} site:razorpay.com OR site:bankifsccode.com"
    url = "https://lite.duckduckgo.com/lite/"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.post(url, data={"q": search_q}, headers=headers)

        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            snippets = soup.select(".result-snippet")
            text_corpus = " ".join([s.text for s in snippets])

            # Regex for Indian IFSC code: 4 letters, 0, 6 letters/digits
            matches = re.findall(r"\b[A-Z]{4}0[A-Z0-9]{6}\b", text_corpus.upper())
            if matches:
                found_ifsc = matches[0]
                # Fetch full verified details
                async with httpx.AsyncClient(timeout=10.0) as client:
                    verify_res = await client.get(f"https://ifsc.razorpay.com/{found_ifsc}")
                if verify_res.status_code == 200:
                    data = verify_res.json()
                    bank = data.get("BANK", "Bank")
                    branch = data.get("BRANCH", "Branch")
                    address = data.get("ADDRESS", "Address")
                    return await msg.edit_msg(
                        f"🏦 <b>IFSC Found for:</b> <code>{query}</code>\n\n"
                        f"<b>• Bank:</b> {bank}\n"
                        f"<b>• Branch:</b> {branch}\n"
                        f"<b>• IFSC Code:</b> <code>{found_ifsc}</code>\n"
                        f"<b>• Address:</b> {address}"
                    )

        google_link = f"https://www.google.com/search?q=IFSC+code+{urllib.parse.quote_plus(query)}"
        await msg.edit_msg(
            f"ℹ️ Could not automatically extract exact code.\n"
            f"🔗 <a href='{google_link}'>Search on Google for {query} IFSC</a>",
            disable_web_page_preview=True,
        )
    except Exception as e:
        await msg.edit_msg(f"❌ Error finding IFSC: <code>{e}</code>")
