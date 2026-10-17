# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
import re
import urllib.parse
from typing import List, Dict, Tuple, Optional
from bs4 import BeautifulSoup
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


async def _upload_to_catbox(file_path: str) -> Optional[str]:
    """Upload temporary image to Catbox to obtain a public URL for reverse search engines."""
    url = "https://catbox.moe/user/api.php"
    async with httpx.AsyncClient(timeout=30.0) as client:
        with open(file_path, "rb") as f:
            files = {"fileToUpload": (os.path.basename(file_path), f)}
            data = {"reqtype": "fileupload"}
            res = await client.post(url, data=data, files=files)
            if res.status_code == 200 and res.text.startswith("http"):
                return res.text.strip()
    return None


@Friday.register_on_cmd(
    ["google", "g", "search", "websearch"],
    cmd_help={
        "help": "Search Google & the Web with pagination, detailed snippets, and site filters.",
        "example": "google Telethon python\ng -p 2 linux kernel (page 2)\ngoogle -num 7 rust lang\ng -site github.com fast api",
    },
    requires_input=True,
)
async def google_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for web search.")

    raw = m.user_input.strip()
    page = 1
    limit = 5

    # Check for page flag: -p <page>
    if "-p " in raw:
        parts = raw.split("-p ")
        raw = parts[0].strip()
        try:
            page = int(parts[1].strip().split()[0])
            page = max(1, min(10, page))
        except Exception:
            pass

    # Check for limit flag: -num <limit>
    if "-num " in raw:
        parts = raw.split("-num ")
        raw = parts[0].strip()
        try:
            limit = int(parts[1].strip().split()[0])
            limit = max(1, min(10, limit))
        except Exception:
            pass

    # Check for site filter: -site <domain>
    if "-site " in raw:
        parts = raw.split("-site ")
        raw = parts[0].strip()
        site = parts[1].strip().split()[0]
        raw += f" site:{site}"

    query = raw.strip()
    if not query:
        return await m.handle_message("❌ Please provide a search query.")

    msg = await m.handle_message(f"🔍 Searching web for <b>{query}</b> (Page {page})...")

    results = []

    try:
        # Calculate pagination offset
        offset = (page - 1) * 15
        url = "https://lite.duckduckgo.com/lite/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Referer": "https://lite.duckduckgo.com/",
        }
        data = {"q": query}
        if offset > 0:
            data["s"] = str(offset)

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, data=data, headers=headers)

        if res.status_code != 200:
            return await msg.edit_msg("❌ DuckDuckGo search service is temporarily unavailable.")

        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select(".result-link")
        snippets = soup.select(".result-snippet")

        for l_tag, s_tag in zip(links, snippets):
            title = l_tag.text.strip()
            href = l_tag.get("href", "")

            # DuckDuckGo redirect link unquote
            if "/l/?uddg=" in href:
                match = re.search(r"uddg=([^&]+)", href)
                if match:
                    href = urllib.parse.unquote(match.group(1))

            snippet = s_tag.text.strip()
            if title and href:
                # Extract clean domain name
                try:
                    domain = urllib.parse.urlparse(href).netloc.replace("www.", "")
                except Exception:
                    domain = "web"
                results.append((title, href, snippet, domain))

        if not results:
            return await msg.edit_msg(f"🤷‍♂️ No search results found for <code>{query}</code> (Page {page}).")

        entries = []
        for i, (title, link, snip, dom) in enumerate(results[:limit], 1):
            clean_snip = snip[:180] + ("..." if len(snip) > 180 else "")
            entries.append(
                f"<b>{i}.</b> <a href='{link}'><b>{title}</b></a> <i>({dom})</i>\n"
                f"   {clean_snip}"
            )

        report = (
            f"🔍 <b>Web Search Results:</b> <code>{query}</code>\n"
            f"📄 <b>Page {page}</b> (Showing {min(len(results), limit)} of {len(results)} matches)\n\n"
            + "\n\n".join(entries)
            + f"\n\n<i>Use <code>.google {query} -p {page + 1}</code> for next page.</i>"
        )
        await msg.edit_msg(report, disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_msg(f"❌ Web search error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["img", "images", "gis"],
    cmd_help={
        "help": "Search high-definition images and download them directly into Telegram.",
        "example": "img cyberpunk city or img -n 4 minimalist wallpaper",
    },
    requires_input=True,
)
async def image_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    raw = m.user_input.strip()
    limit = 3

    if "-n " in raw:
        parts = raw.split("-n ")
        raw = parts[0].strip()
        try:
            limit = int(parts[1].strip().split()[0])
            limit = max(1, min(8, limit))
        except Exception:
            pass

    msg = await m.handle_message(f"🖼 Fetching images for <b>{raw}</b> (Quantity: {limit})...")

    try:
        # Step 1: Request DDG Token
        token_url = f"https://duckduckgo.com/?q={urllib.parse.quote(raw)}&iax=images&ia=images"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_res = await client.get(token_url, headers=headers)
            vqd = None
            match = re.search(r"vqd=([0-9-]+)", token_res.text) or re.search(r'vqd="([0-9-]+)"', token_res.text)
            if match:
                vqd = match.group(1)

        if not vqd:
            # Fallback Unsplash zero-key search
            un_url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(raw)}&per_page={limit}&client_id=your_client_id"
            return await msg.edit_msg("❌ Could not obtain search session token.")

        # Step 2: Fetch Image Links
        img_api = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={urllib.parse.quote(raw)}&vqd={vqd}&f=,,,&p=1"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(img_api, headers=headers)

        if res.status_code != 200:
            return await msg.edit_msg("❌ Failed to fetch image results.")

        items = res.json().get("results", [])
        if not items:
            return await msg.edit_msg(f"🤷‍♂️ No images found for <code>{raw}</code>.")

        os.makedirs("temp/xtra_search", exist_ok=True)
        sent_count = 0
        target_chat = m.chat_id or getattr(m.chat, "id", None)

        for item in items[:limit]:
            img_url = item.get("image")
            if not img_url:
                continue

            local_file = os.path.join("temp/xtra_search", f"img_{sent_count}_{m.id}.jpg")
            try:
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as dl_client:
                    img_resp = await dl_client.get(img_url)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        with open(local_file, "wb") as f:
                            f.write(img_resp.content)

                        title = item.get("title", raw)
                        source = item.get("source", "Web")
                        await c.send_file(
                            target_chat,
                            local_file,
                            caption=f"🖼 <b>{title}</b>\n<i>Source: {source}</i>",
                            reply_to=m.id,
                        )
                        sent_count += 1
            except Exception:
                pass
            finally:
                if os.path.exists(local_file):
                    os.remove(local_file)

        if sent_count > 0:
            try:

                await msg.delete()

            except Exception:

                pass
        else:
            await msg.edit_msg("❌ Failed to download found image links.")
    except Exception as e:
        await msg.edit_msg(f"❌ Image search error: <code>{e}</code>")


@Friday.register_on_cmd(
    ["reverse", "ris", "yandex", "grs"],
    cmd_help={
        "help": "Reverse image search replied photo/sticker across Google Lens, Yandex, Bing, TinEye, SauceNAO, and TraceMoe.",
        "example": "reverse (replying to photo/sticker/image)",
    },
    requires_reply=True,
)
async def multi_reverse_search(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    rm = m.reply_to_message or (await m.get_reply_message() if hasattr(m, "get_reply_message") else None)
    if not rm or not (rm.photo or rm.sticker or (rm.file and rm.file.mime_type and rm.file.mime_type.startswith("image/"))):
        return await m.handle_message("❌ Please reply to a photo, sticker, or image.")

    msg = await m.handle_message("🔍 Uploading media to high-speed visual reconnaissance engines...")
    os.makedirs("temp/xtra_search", exist_ok=True)
    local_path = await rm.download_media("temp/xtra_search/")

    if not local_path or not os.path.exists(local_path):
        return await msg.edit_msg("❌ Failed to download replied media.")

    try:
        # Upload to Catbox
        image_url = await _upload_to_catbox(local_path)
        if not image_url:
            return await msg.edit_msg("❌ Failed to upload image to host for reverse search.")

        enc_url = urllib.parse.quote_plus(image_url)

        # Multi-engine links
        google_lens = f"https://lens.google.com/uploadbyurl?url={enc_url}"
        google_images = f"https://www.google.com/searchbyimage?image_url={enc_url}"
        yandex_images = f"https://yandex.com/images/search?rpt=imageview&url={enc_url}"
        bing_visual = f"https://www.bing.com/images/searchbyimage?cbir=sbi&imgurl={enc_url}"
        tineye = f"https://tineye.com/search?url={enc_url}"
        saucenao = f"https://saucenao.com/search.php?url={enc_url}"
        tracemoe = f"https://trace.moe/?url={enc_url}"

        # Probe Yandex for best match
        best_guess = "Analyzing..."
        detected_tags = []
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                yres = await client.get(yandex_images, headers={"User-Agent": "Mozilla/5.0"})
                if yres.status_code == 200:
                    soup = BeautifulSoup(yres.text, "html.parser")
                    tags = soup.select(".Tags-Item")
                    if tags:
                        detected_tags = [t.text.strip() for t in tags[:5]]
                        best_guess = ", ".join(detected_tags)
                    # Check for title
                    title_elem = soup.select_one(".CbirItem-Title")
                    if title_elem:
                        best_guess = title_elem.text.strip()
        except Exception:
            pass

        if best_guess == "Analyzing...":
            best_guess = "Visual scene / Object"

        report = (
            "🔎 <b>Multi-Engine Visual Reverse Search</b>\n\n"
            f"• <b>Best Match / Identification:</b>\n"
            f"  ➔ <code>{best_guess}</code>\n\n"
            f"<b>Explore Results Across Global Engines:</b>\n"
            f"🔴 <a href='{google_lens}'>Google Lens</a> | <a href='{google_images}'>Google Images</a>\n"
            f"🟡 <a href='{yandex_images}'>Yandex Visual Search</a>\n"
            f"🔵 <a href='{bing_visual}'>Bing Visual Match</a>\n"
            f"⚪ <a href='{tineye}'>TinEye Exact Match</a>\n"
            f"🟣 <a href='{tracemoe}'>Trace.moe (Anime Frame Search)</a>\n"
            f"🟢 <a href='{saucenao}'>SauceNAO (Manga & Pixiv Art)</a>"
        )
        await msg.edit_msg(report, disable_web_page_preview=False)
    except Exception as e:
        await msg.edit_msg(f"❌ Reverse search error: <code>{e}</code>")
    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass
