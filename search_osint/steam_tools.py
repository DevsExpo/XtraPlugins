# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import httpx
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message


@Friday.register_on_cmd(
    ["steam", "game", "steamgame"],
    cmd_help={
        "help": "Search the Steam store for PC game prices, discounts, metacritic scores, and platform specs.",
        "example": "steam Cyberpunk 2077\nsteam Elden Ring\nsteam Portal 2",
    },
    requires_input=True,
)
async def steam_search_cmd(c: Client, m: Message):
    query = m.user_input.strip()
    msg = await m.handle_message(f"🎮 Searching Steam store for <b>{query}</b>...")

    search_url = "https://store.steampowered.com/api/storesearch/"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            s_resp = await client.get(search_url, params={"term": query, "l": "english", "cc": "US"})
            if s_resp.status_code != 200:
                return await msg.edit_msg("❌ Steam API query failed.")
            s_data = s_resp.json()

        items = s_data.get("items", [])
        if not items:
            return await msg.edit_msg(f"🤷‍♂️ No Steam games found matching <code>{query}</code>.")

        first_game = items[0]
        app_id = first_game.get("id")

        # Fetch detailed app specs
        details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=US"
        async with httpx.AsyncClient(timeout=12.0) as client:
            d_resp = await client.get(details_url)
            d_data = d_resp.json() if d_resp.status_code == 200 else {}

        app_info = d_data.get(str(app_id), {}).get("data", {}) if d_data else {}

        name = app_info.get("name") or first_game.get("name")
        steam_url = f"https://store.steampowered.com/app/{app_id}"
        header_img = app_info.get("header_image")

        is_free = app_info.get("is_free", False)
        price_info = app_info.get("price_overview", {})
        if is_free:
            price_str = "🟢 <b>Free to Play</b>"
        elif price_info:
            final_fmt = price_info.get("final_formatted", "N/A")
            discount = price_info.get("discount_percent", 0)
            if discount > 0:
                initial_fmt = price_info.get("initial_formatted", "")
                price_str = f"<s>{initial_fmt}</s> ➔ <b>{final_fmt}</b> (🔥 <code>-{discount}% OFF</code>)"
            else:
                price_str = f"<b>{final_fmt}</b>"
        else:
            price_str = "<i>Price Unavailable</i>"

        metacritic = app_info.get("metacritic", {}).get("score", "N/A")
        genres = ", ".join(g.get("description") for g in app_info.get("genres", [])[:3]) or "Game"
        release_date = app_info.get("release_date", {}).get("date", "Unknown")

        platforms = app_info.get("platforms", {})
        plat_icons = []
        if platforms.get("windows"):
            plat_icons.append("Windows")
        if platforms.get("mac"):
            plat_icons.append("macOS")
        if platforms.get("linux"):
            plat_icons.append("Linux/SteamDeck")
        plat_str = ", ".join(plat_icons) if plat_icons else "PC"

        desc = app_info.get("short_description") or ""
        desc_snippet = f'<i>"{desc[:200]}..."</i>' if desc else ""

        report = (
            f"🎮 <b><a href='{steam_url}'>{name}</a></b>\n\n"
            f"💰 <b>Price:</b> {price_str}\n"
            f"⭐ <b>Metacritic Score:</b> <code>{metacritic}/100</code>\n"
            f"🏷 <b>Genres:</b> <code>{genres}</code>\n"
            f"💻 <b>Platforms:</b> <code>{plat_str}</code>\n"
            f"📅 <b>Release Date:</b> <code>{release_date}</code>\n\n"
            f"{desc_snippet}"
        )

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        if header_img:
            await c.send_file(
                target_chat,
                header_img,
                caption=report,
                reply_to=m.id,
            )
            await msg.delete()
        else:
            await msg.edit_msg(report, disable_web_page_preview=False)

    except Exception as e:
        await msg.edit_msg(f"❌ Steam error: <code>{e}</code>")
