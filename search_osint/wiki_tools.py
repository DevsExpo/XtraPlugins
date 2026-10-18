# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import urllib.parse
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


@Friday.register_on_cmd(
    ["wiki", "wikipedia"],
    cmd_help={
        "help": "Search Wikipedia articles with full extracts, thumbnail photos, and multi-language support (-es, -fr, -de, -hi, -ru).",
        "example": "wiki Albert Einstein\nwiki Quantum Computing -fr\nwiki James Webb Space Telescope",
    },
    requires_input=True,
)
async def wiki_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for Wikipedia.")

    raw = m.user_input.strip()
    lang = "en"

    parts = raw.split()
    query_parts = []
    for p in parts:
        if p.startswith("-") and len(p) in (3, 4) and p[1:].isalpha():
            lang = p[1:].lower()
        else:
            query_parts.append(p)

    query = " ".join(query_parts).strip()
    if not query:
        return await m.handle_message("❌ Please provide a search query: <code>.wiki Albert Einstein</code>")

    msg = await m.handle_message(f"📖 Querying Wikipedia ({lang.upper()}) for <b>{query}</b>...")

    encoded_title = urllib.parse.quote(query.replace(" ", "_"))
    api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.get(
                api_url, headers={"User-Agent": "FridayUserbot/1.0 (https://github.com/FridaySoftware)"}
            )

        if res.status_code == 404:
            # Fallback to search query API
            search_api = f"https://{lang}.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(query)}&limit=3&format=json"
            async with httpx.AsyncClient(timeout=15.0) as client:
                search_res = await client.get(search_api, headers={"User-Agent": "FridayUserbot/1.0"})
            if search_res.status_code == 200:
                sdata = search_res.json()
                if len(sdata) > 1 and sdata[1]:
                    first_match = sdata[1][0]
                    # Retry summary with first match
                    retry_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(first_match.replace(' ', '_'))}"
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        rres = await client.get(retry_url, headers={"User-Agent": "FridayUserbot/1.0"})
                    if rres.status_code == 200:
                        res = rres
                    else:
                        suggestions = "\n".join(
                            [f"• <a href='{sdata[3][i]}'>{sdata[1][i]}</a>" for i in range(len(sdata[1]))]
                        )
                        return await msg.edit_msg(
                            f'📖 <b>Wikipedia Matches for "{query}":</b>\n\n{suggestions}\n\n<i>Search with exact title above.</i>'
                        )
            if res.status_code == 404:
                return await msg.edit_msg(f"❌ No Wikipedia article found for <code>{query}</code>.")

        if res.status_code != 200:
            return await msg.edit_msg(f"❌ Wikipedia API error (HTTP {res.status_code}).")

        data = res.json()
        title = data.get("title", query)
        description = data.get("description", "")
        extract = data.get("extract", "No summary available.")
        page_url = (
            data.get("content_urls", {})
            .get("desktop", {})
            .get("page", f"https://{lang}.wikipedia.org/wiki/{encoded_title}")
        )

        # Check for thumbnail image
        thumbnail_obj = data.get("originalimage") or data.get("thumbnail")
        image_url = thumbnail_obj.get("source") if thumbnail_obj else None

        desc_block = f"<i>({description})</i>\n\n" if description else ""
        caption = (
            f"📖 <b>{title}</b>\n"
            f"{desc_block}"
            f"{extract[:1500]}\n\n"
            f"🔗 <a href='{page_url}'>Read full article on Wikipedia</a>"
        )

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        if image_url and image_url.startswith("http"):
            await c.send_file(target_chat, image_url, caption=caption, reply_to=m.id)
            try:
                await msg.delete()
            except Exception:
                pass
            return

        await msg.edit_msg(caption, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ Wikipedia search error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["wikirand", "wikirandom"],
    cmd_help={
        "help": "Discover a completely random fascinating Wikipedia article.",
        "example": "wikirand or wikirand -es",
    },
)
async def random_wiki(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    lang = "en"
    if m.user_input and m.user_input.startswith("-") and len(m.user_input) in (3, 4):
        lang = m.user_input[1:].lower()

    msg = await m.handle_message("🎲 Fetching a random article from Wikipedia...")
    try:
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/random/summary"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers={"User-Agent": "FridayUserbot/1.0"})

        if res.status_code != 200:
            return await msg.edit_msg("❌ Failed to fetch random article.")

        data = res.json()
        title = data.get("title")
        description = data.get("description", "")
        extract = data.get("extract", "")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
        thumbnail_obj = data.get("originalimage") or data.get("thumbnail")
        image_url = thumbnail_obj.get("source") if thumbnail_obj else None

        desc_block = f"<i>({description})</i>\n\n" if description else ""
        caption = (
            f"🎲 <b>Random Discovery: {title}</b>\n"
            f"{desc_block}"
            f"{extract[:1500]}\n\n"
            f"🔗 <a href='{page_url}'>Read full article</a>"
        )

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        if image_url and image_url.startswith("http"):
            await c.send_file(target_chat, image_url, caption=caption, reply_to=m.id)
            try:
                await msg.delete()
            except Exception:
                pass
            return

        await msg.edit_msg(caption)
    except Exception as e:
        await msg.edit_msg(f"❌ Random Wikipedia error: <code>{e}</code>")
