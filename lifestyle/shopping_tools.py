# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

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
    ["shop", "price", "product"],
    cmd_help={
        "help": "Search product listings and store links across Amazon, eBay, and Google Shopping.",
        "example": "shop mechanical keyboard\nprice RTX 4080",
    },
    requires_input=True,
)
async def search_shopping(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for shopping search.")

    query = m.user_input.strip()
    msg = await m.handle_message(f"🛍 Searching stores for <b>{query}</b>...")

    encoded_query = urllib.parse.quote_plus(query)
    amazon_link = f"https://www.amazon.com/s?k={encoded_query}"
    ebay_link = f"https://www.ebay.com/sch/i.html?_nkw={encoded_query}"
    google_shop = f"https://www.google.com/search?tbm=shop&q={encoded_query}"
    aliexpress_link = f"https://www.aliexpress.com/wholesale?SearchText={encoded_query}"

    results_list = []

    try:
        search_query = f"buy {query} price site:amazon.com OR site:ebay.com"
        url = "https://lite.duckduckgo.com/lite/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://duckduckgo.com/",
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.post(url, data={"q": search_query}, headers=headers)

        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            links = soup.select(".result-link")
            snippets = soup.select(".result-snippet")

            count = min(len(links), 4)
            for i in range(count):
                title = links[i].text.strip()
                href = links[i].get("href", "")
                snippet = snippets[i].text.strip() if i < len(snippets) else ""

                store = "Amazon" if "amazon" in href.lower() else ("eBay" if "ebay" in href.lower() else "Store")
                if title and href:
                    results_list.append(
                        f"• <b><a href='{href}'>{title}</a></b> ({store})\n  <i>{snippet[:140]}...</i>"
                        if len(snippet) > 140
                        else f"• <b><a href='{href}'>{title}</a></b> ({store})\n  <i>{snippet}</i>"
                    )

        if results_list:
            report = (
                f"🛍 <b>Shopping Results:</b> <code>{query}</code>\n\n"
                + "\n\n".join(results_list)
                + f"\n\n🔗 <b>Compare:</b> <a href='{amazon_link}'>Amazon</a> | <a href='{ebay_link}'>eBay</a> | <a href='{google_shop}'>Google Shopping</a> | <a href='{aliexpress_link}'>AliExpress</a>"
            )
        else:
            report = (
                f"🛍 <b>Shopping Search:</b> <code>{query}</code>\n\n"
                f"🛒 <a href='{amazon_link}'>Amazon</a>\n"
                f"🏷 <a href='{ebay_link}'>eBay</a>\n"
                f"🔍 <a href='{google_shop}'>Google Shopping</a>\n"
                f"📦 <a href='{aliexpress_link}'>AliExpress</a>"
            )

        await msg.edit_msg(report, disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_msg(f"❌ Shopping search error: <code>{e}</code>")
