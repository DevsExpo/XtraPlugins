# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Tuple

import aiohttp
from telethon import Button
from telethon.errors.rpcerrorlist import MessageNotModifiedError

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message
from Main.core.decorators import log_errors
from Main.utils.inline_helper import send_inline_widget
from XtraPlugins.ui_tokens import NEWS, STATUS

logger = logging.getLogger("friday.news")


_FEEDS = {
    "top": {
        "title": "Top Headlines (India & Global)",
        "url": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
    },
    "tech": {
        "title": "Technology & AI",
        "url": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en",
    },
    "business": {
        "title": "Business & Finance",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en",
    },
    "world": {
        "title": "World & Geopolitics",
        "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    },
    "science": {
        "title": "Science & Space",
        "url": "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-IN&gl=IN&ceid=IN:en",
    },
    "sports": {
        "title": "Sports & Cricket",
        "url": "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=en-IN&gl=IN&ceid=IN:en",
    },
    "entertainment": {
        "title": "Entertainment & Cinema",
        "url": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-IN&gl=IN&ceid=IN:en",
    },
}

_NEWS_CACHE: Dict[str, Tuple[List[Dict[str, str]], float]] = {}


def _clean_html(raw_html: str) -> str:
    clean = re.sub(r"<[^>]+>", "", raw_html or "")
    return html.unescape(clean).strip()


async def _fetch_news_feed(topic_or_query: str) -> List[Dict[str, str]]:
    key = topic_or_query.lower().strip()

    if key in _NEWS_CACHE:
        items, ts = _NEWS_CACHE[key]
        if (asyncio.get_event_loop().time() - ts) < 300:
            return items

    if key in _FEEDS:
        url = _FEEDS[key]["url"]
    else:
        encoded = urllib.parse.quote_plus(key)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return []
                xml_text = await resp.text()

        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            return []

        articles: List[Dict[str, str]] = []
        for item in channel.findall("item"):
            title_elem = item.find("title")
            link_elem = item.find("link")
            pub_date_elem = item.find("pubDate")
            source_elem = item.find("source")

            raw_title = title_elem.text if title_elem is not None else "Untitled"
            source_name = source_elem.text if source_elem is not None else ""
            if not source_name and " - " in raw_title:
                parts = raw_title.rsplit(" - ", 1)
                title = parts[0]
                source_name = parts[1]
            else:
                title = raw_title

            link = link_elem.text if link_elem is not None else ""
            pub_date = pub_date_elem.text if pub_date_elem is not None else ""

            rel_time = ""
            if pub_date:
                try:
                    dt = datetime.strptime(pub_date[:25].strip(), "%a, %d %b %Y %H:%M:%S")
                    diff = (datetime.utcnow() - dt).total_seconds()
                    if diff < 3600:
                        rel_time = f"{int(max(1, diff // 60))}m ago"
                    elif diff < 86400:
                        rel_time = f"{int(diff // 3600)}h ago"
                    else:
                        rel_time = f"{int(diff // 86400)}d ago"
                except Exception:
                    rel_time = pub_date[:16]

            articles.append(
                {
                    "title": _clean_html(title),
                    "source": source_name.strip() or "News Desk",
                    "link": link,
                    "time": rel_time,
                }
            )

            if len(articles) >= 25:
                break

        _NEWS_CACHE[key] = (articles, asyncio.get_event_loop().time())
        return articles

    except Exception as exc:
        logger.warning(f"Failed to fetch news feed '{topic_or_query}': {exc}")
        return []


def _render_articles_page(
    articles: List[Dict[str, str]],
    page: int,
    per_page: int = 5,
    query_title: str = "Top News",
    is_inline: bool = True,
    category_key: str = "top",
    pfx: str = ".",
) -> str:
    total = len(articles)
    if total == 0:
        return f"📰 <b>News: {html.escape(query_title)}</b>\n\n<i>No recent news stories found for this topic.</i>"

    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = min(start + per_page, total)
    subset = articles[start:end]

    lines = [
        f"{NEWS.ICON} <b>Friday Smart News</b> | <code>{html.escape(query_title)}</code>",
        f"<i>Page {page} of {total_pages} (Stories {start + 1}–{end} of {total})</i>\n",
    ]

    for i, a in enumerate(subset, start=start + 1):
        src = f" [<b>{html.escape(a['source'])}</b>]" if a.get("source") else ""
        time_tag = f" • <i>{a['time']}</i>" if a.get("time") else ""
        title = html.escape(a["title"])
        link = a.get("link")

        if link:
            lines.append(f'<b>{i}.</b> <a href="{link}">{title}</a>{src}{time_tag}')
        else:
            lines.append(f"<b>{i}.</b> {title}{src}{time_tag}")

    if is_inline:
        lines.append(f"\n<i>{STATUS.TIP} Tap buttons below to flip pages, switch topics, or generate a digest.</i>")
    else:
        # Clear CLI Navigation instructions for fallback mode
        next_pg = page + 1 if page < total_pages else 1
        lines.append(f"\n{STATUS.CLI} <b>CLI Navigation (Text Mode):</b>")
        lines.append(f"• <b>Next Page:</b> <code>{pfx}news {category_key} {next_pg}</code>")
        lines.append(
            f"• <b>Switch Topic:</b> <code>{pfx}news tech</code> | <code>{pfx}news biz</code> | <code>{pfx}news sports</code> | <code>{pfx}news world</code>"
        )
        lines.append(f"• <b>TL;DR Digest:</b> <code>{pfx}newsdigest {category_key}</code>")

    return "\n".join(lines)


def _build_news_buttons(category: str, page: int, total_pages: int) -> List[List[Button]]:
    nav_row = []
    if page > 1:
        nav_row.append(Button.inline("◀ Prev", data=f"news:p:{category}:{page - 1}"))
    nav_row.append(Button.inline(f"{NEWS.ICON} {page}/{total_pages}", data="news:noop"))
    if page < total_pages:
        nav_row.append(Button.inline("Next ▶", data=f"news:p:{category}:{page + 1}"))

    cat_row1 = [
        Button.inline(f"{NEWS.TOP} Top", data="news:c:top:1"),
        Button.inline(f"{NEWS.TECH} Tech", data="news:c:tech:1"),
        Button.inline(f"{NEWS.BUSINESS} Biz", data="news:c:business:1"),
    ]
    cat_row2 = [
        Button.inline(f"{NEWS.SPORTS} Sports", data="news:c:sports:1"),
        Button.inline(f"{NEWS.WORLD} World", data="news:c:world:1"),
        Button.inline(f"{NEWS.FLASH} Digest", data=f"news:d:{category}"),
    ]

    return [nav_row, cat_row1, cat_row2]


@Friday.register_on_cmd(
    ["news", "headlines", "samachar"],
    cmd_help={
        "help": "Smart real-time news aggregator with category filters, keyword search, and TL;DR digests. Supports interactive buttons and CLI navigation.",
        "example": [
            "news",
            "news tech",
            "news tech 2 (page 2)",
            "news isro",
            "news -text (force plain text mode)",
        ],
    },
)
@log_errors
async def news_cmd(c: Client, m: Message):
    raw_input = (m.user_input or "top").strip()
    force_text = "-text" in raw_input or "-cli" in raw_input
    clean_input = raw_input.replace("-text", "").replace("-cli", "").strip()

    args = clean_input.split() if clean_input else ["top"]
    page = 1
    if len(args) >= 2 and args[-1].isdigit():
        page = max(1, int(args[-1]))
        query = " ".join(args[:-1]).lower()
    elif len(args) == 1 and args[0].isdigit():
        page = max(1, int(args[0]))
        query = "top"
    else:
        query = " ".join(args).lower()

    alias_map = {
        "india": "top",
        "tech": "tech",
        "technology": "tech",
        "ai": "tech",
        "biz": "business",
        "finance": "business",
        "market": "business",
        "markets": "business",
        "cricket": "sports",
        "sport": "sports",
        "space": "science",
        "movies": "entertainment",
    }
    category = alias_map.get(query, query)

    # 1. Attempt interactive inline widget if not forced to text
    if not force_text:
        try:
            if await send_inline_widget(c, m, f"news:{category}:{page}"):
                return
        except Exception as e:
            logger.debug(f"News send_inline_widget failed, falling back to text: {e}")

    # 2. Text / CLI Fallback Mode
    status_msg = await m.handle_message(f"📡 <i>Fetching latest news on <b>{html.escape(category.title())}</b>...</i>")

    pfx = getattr(m, "prefix", None) or getattr(Friday, "user_command_handler", ".") or "."
    articles = await _fetch_news_feed(category)
    if not articles:
        return await status_msg.edit_msg(
            f"❌ <b>No news stories found</b> for <code>{html.escape(query)}</code>.\n"
            f"Try categories: <code>{pfx}news tech</code>, <code>{pfx}news business</code>, <code>{pfx}news sports</code>, <code>{pfx}news isro</code>"
        )

    title_label = _FEEDS[category]["title"] if category in _FEEDS else f"Search: {category.title()}"
    per_page = 5

    # Render without misleading button prompt
    text = _render_articles_page(articles, page, per_page, title_label, is_inline=False, category_key=category, pfx=pfx)
    await status_msg.edit_msg(text, parse_mode="html", link_preview=False)


@Friday.register_on_cmd(
    ["newsdigest", "tldrnews"],
    cmd_help={
        "help": "Get a rapid executive bulleted digest of top stories.",
        "example": ["newsdigest", "newsdigest tech", "newsdigest crypto"],
    },
)
@log_errors
async def news_digest_cmd(c: Client, m: Message):
    query = (m.user_input or "top").strip().lower()
    status_msg = await m.handle_message(
        f"⚡ <i>Synthesizing executive news digest for <b>{html.escape(query.title())}</b>...</i>"
    )

    articles = await _fetch_news_feed(query)
    if not articles:
        return await status_msg.edit_msg(f"❌ No news found for <code>{html.escape(query)}</code>.")

    top_stories = articles[:7]
    bullets = [f"⚡ <b>Executive News Briefing — {html.escape(query.title())}</b>\n"]
    for i, a in enumerate(top_stories, 1):
        bullets.append(f"• <b>{html.escape(a['title'])}</b> (<i>{html.escape(a['source'])}</i>)")

    bullets.append("\n<i>Stay informed, stay ahead.</i>")
    await status_msg.edit_msg("\n".join(bullets), parse_mode="html")


if hasattr(Friday, "bot") and Friday.bot is not None:

    @Friday.bot.on_inline_query(pattern=r"^news(?::([^:]+))?(?::(\d+))?$")
    async def on_news_inline_query(event):
        """Build interactive inline widget response for userbot query."""
        match = event.pattern_match
        category = (match.group(1) or "top").strip().lower()
        page = int(match.group(2)) if match.group(2) and match.group(2).isdigit() else 1

        articles = await _fetch_news_feed(category)
        title_label = _FEEDS[category]["title"] if category in _FEEDS else f"Search: {category.title()}"
        per_page = 5
        total_pages = max(1, (len(articles) + per_page - 1) // per_page)

        text = _render_articles_page(articles, page, per_page, title_label, is_inline=True, category_key=category)
        buttons = _build_news_buttons(category, page, total_pages)

        builder = event.builder
        result = builder.article(
            title=f"📰 Friday News: {title_label}",
            description=f"Browse {len(articles)} stories interactively",
            text=text,
            buttons=buttons,
            parse_mode="html",
            link_preview=False,
        )
        await event.answer([result], cache_time=30)


if hasattr(Friday, "bot") and Friday.bot is not None:

    @Friday.bot.on_callback_query(pattern=r"^news:(p|c|d|noop):?([^:]+)?:?(\d+)?$")
    async def on_news_callback(event):
        data = event.data.decode("utf-8")
        parts = data.split(":")
        action = parts[1]

        if action == "noop":
            return await event.answer()

        category = parts[2] if len(parts) > 2 else "top"
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

        await event.answer("🔄 Updating feed...", alert=False)

        articles = await _fetch_news_feed(category)
        if not articles:
            return await event.respond("❌ Feed is currently unavailable.")

        title_label = _FEEDS[category]["title"] if category in _FEEDS else f"Search: {category.title()}"

        if action == "d":
            top_stories = articles[:7]
            bullets = [f"⚡ <b>Executive News Digest — {html.escape(title_label)}</b>\n"]
            for i, a in enumerate(top_stories, 1):
                bullets.append(
                    f'• <a href="{a["link"]}">{html.escape(a["title"])}</a> (<i>{html.escape(a["source"])}</i>)'
                )
            bullets.append("\n<i>Tap any headline to read the full source report.</i>")

            back_btn = [[Button.inline("🔙 Back to News List", data=f"news:c:{category}:1")]]
            with contextlib.suppress(MessageNotModifiedError):
                await event.edit("\n".join(bullets), buttons=back_btn, parse_mode="html", link_preview=False)
            return

        per_page = 5
        total_pages = max(1, (len(articles) + per_page - 1) // per_page)
        text = _render_articles_page(articles, page, per_page, title_label, is_inline=True, category_key=category)
        buttons = _build_news_buttons(category, page, total_pages)

        with contextlib.suppress(MessageNotModifiedError):
            await event.edit(text, buttons=buttons, parse_mode="html", link_preview=False)
