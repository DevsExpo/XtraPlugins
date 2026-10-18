# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import time
import json
import urllib.parse
from typing import Dict, Any
from bs4 import BeautifulSoup
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

OMDB_API_KEY = os.getenv("OMDB_API_KEY")


async def _scrape_imdb_details(imdb_id: str) -> Dict[str, Any]:
    """Scrape rich JSON-LD data from IMDb title page without requiring an API key."""
    url = f"https://www.imdb.com/title/{imdb_id}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    details = {}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                script = soup.find("script", type="application/ld+json")
                if script and script.string:
                    data = json.loads(script.string)
                    details["plot"] = data.get("description")
                    rating_obj = data.get("aggregateRating", {})
                    if rating_obj:
                        details["rating"] = rating_obj.get("ratingValue")
                        details["rating_count"] = rating_obj.get("ratingCount")
                    details["genre"] = (
                        ", ".join(data.get("genre", [])) if isinstance(data.get("genre"), list) else data.get("genre")
                    )
                    directors = data.get("director", [])
                    if isinstance(directors, list):
                        details["director"] = ", ".join([d.get("name", "") for d in directors if "name" in d])
                    elif isinstance(directors, dict):
                        details["director"] = directors.get("name")
                    actors = data.get("actor", [])
                    if isinstance(actors, list):
                        details["actors"] = ", ".join([a.get("name", "") for a in actors[:4] if "name" in a])
                    if data.get("image"):
                        details["image"] = data.get("image")
    except Exception:
        pass
    return details


@Friday.register_on_cmd(
    ["movie", "imdb", "film", "series"],
    cmd_help={
        "help": "Search movies, anime, and TV series for ratings, plot summaries, cast, and posters.",
        "example": "movie Inception\nimdb Breaking Bad\nfilm Spirited Away",
    },
    requires_input=True,
)
async def movie_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    query = m.user_input.strip()
    msg = await m.handle_message(f"🎬 Searching IMDb database for <b>{query}</b>...")

    # Method 1: If OMDB_API_KEY is configured
    if OMDB_API_KEY:
        try:
            omdb_url = f"https://www.omdbapi.com/?t={urllib.parse.quote(query)}&apikey={OMDB_API_KEY}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(omdb_url)
            if res.status_code == 200 and res.json().get("Response") == "True":
                data = res.json()
                title = data.get("Title")
                year = data.get("Year")
                rated = data.get("Rated", "N/A")
                runtime = data.get("Runtime", "N/A")
                genre = data.get("Genre", "N/A")
                director = data.get("Director", "N/A")
                actors = data.get("Actors", "N/A")
                plot = data.get("Plot", "No plot summary.")
                imdb_rating = data.get("imdbRating", "N/A")
                poster = data.get("Poster")
                imdb_id = data.get("imdbID")
                imdb_url = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else ""

                caption = (
                    f"🎬 <b>{title} ({year})</b>\n"
                    f"⭐ <b>IMDb:</b> <code>{imdb_rating}/10</code> | <code>{rated}</code> | <code>{runtime}</code>\n"
                    f"<b>• Genre:</b> {genre}\n"
                    f"<b>• Director:</b> {director}\n"
                    f"<b>• Cast:</b> {actors}\n\n"
                    f'<b>Synopsis:</b>\n<i>"{plot}"</i>\n\n'
                    f"🔗 <a href='{imdb_url}'>View Details on IMDb</a>"
                )
                if poster and poster.startswith("http"):
                    target_chat = m.chat_id or getattr(m.chat, "id", None)
                    await c.send_file(target_chat, poster, caption=caption, reply_to=m.id)
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                    return
                return await msg.edit_msg(caption)
        except Exception:
            pass

    # Method 2: Zero-Key Official IMDb Suggestion API + Deep Scrape
    try:
        clean_q = query.lower().replace(" ", "_")
        imdb_url = f"https://v3.sg.media-imdb.com/suggestion/x/{clean_q}.json"

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(imdb_url, headers={"User-Agent": "Mozilla/5.0"})

        if res.status_code != 200:
            return await msg.edit_msg(f"❌ IMDb service returned HTTP {res.status_code}.")

        items = res.json().get("d", [])
        if not items:
            return await msg.edit_msg(f"🤷‍♂️ No movies found matching <code>{query}</code>.")

        first = items[0]
        title = first.get("l", query.title())
        year = first.get("y", "N/A")
        stars = first.get("s", "N/A")
        kind = first.get("q", "feature").replace("_", " ").title()
        imdb_id = first.get("id", "")
        rank = first.get("rank", "N/A")

        poster_obj = first.get("i", {})
        poster_url = poster_obj.get("imageUrl") if poster_obj else None

        # Fetch deep details if imdb_id exists
        extra = {}
        if imdb_id:
            extra = await _scrape_imdb_details(imdb_id)

        plot = extra.get("plot") or "No synopsis available."
        rating = extra.get("rating")
        rating_str = f"⭐ <b>Rating:</b> <code>{rating}/10</code> | " if rating else ""
        genre_str = f"<b>• Genre:</b> {extra.get('genre')}\n" if extra.get("genre") else ""
        director_str = f"<b>• Director:</b> {extra.get('director')}\n" if extra.get("director") else ""

        if not poster_url and extra.get("image"):
            poster_url = extra.get("image")

        page_link = (
            f"https://www.imdb.com/title/{imdb_id}/"
            if imdb_id
            else f"https://www.imdb.com/find?q={urllib.parse.quote(title)}"
        )
        trailer_link = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote(title + ' ' + str(year) + ' trailer')}"
        )

        caption = (
            f"🎬 <b>{title} ({year})</b>\n"
            f"{rating_str}<b>Rank:</b> <code>#{rank}</code> | <code>{kind}</code>\n"
            f"{genre_str}"
            f"{director_str}"
            f"<b>• Starring:</b> {stars}\n\n"
            f'<b>Synopsis:</b>\n<i>"{plot}"</i>\n'
        )

        token = str(int(time.time() * 1000))[-8:]
        _movie_cache[token] = {
            "title": f"{title} ({year})",
            "caption": caption,
            "page_link": page_link,
            "trailer_link": trailer_link,
        }

        if "-basic" not in m.user_args and "-text" not in m.user_args:
            try:
                from Main.utils.inline_helper import send_inline_widget

                if await send_inline_widget(c, m, f"movie:{token}"):
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                    return
            except Exception:
                pass

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        if poster_url and poster_url.startswith("http"):
            await c.send_file(target_chat, poster_url, caption=caption, reply_to=m.id)
            try:
                await msg.delete()
            except Exception:
                pass
            return

        await msg.edit_msg(caption)
    except Exception as e:
        await msg.edit_msg(f"❌ Movie search error: <code>{e}</code>")


# ==========================================
# Interactive Inline Movie Card Handler
# ==========================================

_movie_cache = {}

if getattr(Friday, "bot", None):
    import re
    from telethon import custom
    from Main.utils.custom_filters import filters

    @Friday.bot.on_inline_query(filters.regex(r"^movie:(\w+)"))
    async def movie_inline_query_handler(c, iq):
        m = re.match(r"^movie:(\w+)", iq.text)
        token = m.group(1) if m else ""
        item = _movie_cache.get(token)
        if not item:
            return

        buttons = [
            [
                custom.Button.url("⭐ View on IMDb", item["page_link"]),
                custom.Button.url("🎬 YouTube Trailer", item["trailer_link"]),
            ]
        ]
        builder = iq.builder
        res = builder.article(
            title=item["title"],
            description="Click to send rich movie card with IMDb & Trailer buttons.",
            text=item["caption"],
            buttons=buttons,
            parse_mode="html",
        )
        await iq.answer([res], cache_time=0)


@Friday.register_on_cmd(
    ["trending", "topmovies"],
    cmd_help={
        "help": "Display currently trending and top-rated movies across global box office.",
        "example": "trending",
    },
)
async def trending_movies(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    msg = await m.handle_message("🎬 Fetching trending titles from global box office...")
    try:
        url = "https://v3.sg.media-imdb.com/suggestion/x/trending.json"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})

        if res.status_code == 200:
            items = res.json().get("d", [])
            lines = []
            for i, it in enumerate(items[:8], 1):
                t = it.get("l")
                y = it.get("y", "N/A")
                s = it.get("s", "N/A")
                mid = it.get("id")
                lines.append(
                    f"<b>{i}.</b> <a href='https://www.imdb.com/title/{mid}/'><b>{t}</b></a> ({y})\n   <i>Cast: {s}</i>"
                )

            report = (
                "🔥 <b>Trending Titles on IMDb:</b>\n\n"
                + "\n\n".join(lines)
                + "\n\n<i>Search any title above using <code>.movie &lt;name&gt;</code></i>"
            )
            return await msg.edit_msg(report, disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_msg(f"❌ Trending error: <code>{e}</code>")
