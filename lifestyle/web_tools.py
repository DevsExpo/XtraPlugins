# Copyright (C) 2021-present by DevsExpo@Github, < https://github.com/DevsExpo >.
#
# This file is part of < https://github.com/DevsExpo/Friday > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/Altriux/Friday/blob/main/LICENSE >
#
# All rights reserved.

import os
from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _clean_url(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


@Friday.register_on_cmd(
    ["webshot", "ss"],
    cmd_help={
        "help": "Capture a full-browser screenshot of a given webpage URL.",
        "example": "webshot https://github.com/DevsExpo",
    },
    requires_input=True,
)
async def web_screenshot(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required for webshot.")

    target_url = _clean_url(m.user_input)
    msg = await m.handle_message(f"📸 Capturing screenshot of <code>{target_url}</code>...")

    screenshot_api = f"https://image.thum.io/get/width/1280/crop/800/noanimate/{target_url}"

    os.makedirs("temp/xtra_web", exist_ok=True)
    out_file = f"temp/xtra_web/webshot_{m.id}.png"

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await client.get(screenshot_api, follow_redirects=True)

        if res.status_code != 200 or len(res.content) < 1000:
            # Fallback to secondary screenshot provider
            alt_api = f"https://mini.s-shot.ru/1024x768/PNG/1024/Z100/?{target_url}"
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.get(alt_api, follow_redirects=True)

        if res.status_code != 200 or len(res.content) < 1000:
            return await msg.edit_msg("❌ Failed to capture screenshot. The webpage may be blocked or unreachable.")

        with open(out_file, "wb") as f:
            f.write(res.content)

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        await c.send_file(
            target_chat,
            out_file,
            caption=f"📸 <b>Webshot:</b> <code>{target_url}</code>",
            reply_to=m.id,
        )
        try:
            await msg.delete()

        except Exception:
            pass
    except Exception as e:
        await msg.edit_msg(f"❌ Screenshot error: <code>{e}</code>")
    finally:
        if os.path.exists(out_file):
            try:
                os.remove(out_file)
            except Exception:
                pass


@Friday.register_on_cmd(
    ["unshorten", "unshort"],
    cmd_help={
        "help": "Follow redirects and unshorten shortened links (bit.ly, t.co, etc.).",
        "example": "unshorten https://bit.ly/example",
    },
    requires_input=True,
)
async def unshorten_link(c: Client, m: Message):
    if not HAS_HTTPX:
        return await m.handle_message("❌ <code>httpx</code> is required.")

    target_url = _clean_url(m.user_input)
    msg = await m.handle_message("🔗 Resolving redirect trail...")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.head(target_url)

        final_url = str(res.url)
        report = (
            "🔗 <b>Link Unshortened:</b>\n\n"
            f"<b>• Original:</b> <code>{target_url}</code>\n"
            f"<b>• Destination:</b> <code>{final_url}</code>\n"
            f"<b>• Status Code:</b> <code>{res.status_code}</code>"
        )
        await msg.edit_msg(report, disable_web_page_preview=True)
    except Exception as e:
        await msg.edit_msg(f"❌ Error unshortening link: <code>{e}</code>")
