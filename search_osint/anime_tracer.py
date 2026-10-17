# Copyright (C) 2021-present by FridaySoftware@Github, < https://github.com/FridaySoftware >.
#
# This file is part of < https://github.com/FridaySoftware/Friday > project,
# and is released under the "GNU v3.0 License Agreement".

import os
import io
import httpx
from PIL import Image

from Main import Friday
from Main.core.types.client import FridayTelegramClient as Client
from Main.core.types.message import Message


@Friday.register_on_cmd(
    ["whatanime", "tracemoe", "findanime", "animeframe"],
    cmd_help={
        "help": "Reverse anime scene search from a replied photo or screenshot via Trace.moe.",
        "example": "whatanime (reply to an anime screenshot or meme)",
    },
    requires_reply=True,
)
async def what_anime_cmd(c: Client, m: Message):
    reply = m.reply_to_message or (await m.get_reply_message())
    if not reply or not (reply.photo or reply.sticker or getattr(reply, "file", None)):
        return await m.handle_message("❌ Please reply to an anime screenshot or image.")

    msg = await m.handle_message("🔍 Searching anime scene database via Trace.moe...")
    out_dir = os.path.join("temp", "anime_trace")
    os.makedirs(out_dir, exist_ok=True)

    input_file = await reply.download_media(file=out_dir)
    if not input_file or not os.path.exists(input_file):
        return await msg.edit_msg("❌ Failed to download replied image.")

    try:
        # Convert image to compressed JPEG for fast upload
        img = Image.open(input_file).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        url = "https://api.trace.moe/search?anilistInfo"
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, files={"image": ("frame.jpg", img_bytes, "image/jpeg")})
            if resp.status_code != 200:
                return await msg.edit_msg(f"❌ Trace.moe query failed (HTTP {resp.status_code}).")
            data = resp.json()

        results = data.get("result", [])
        if not results:
            return await msg.edit_msg("🤷‍♂️ No matching anime scenes found for this frame.")

        best = results[0]
        similarity = best.get("similarity", 0) * 100
        anilist = best.get("anilist", {})
        title_romaji = anilist.get("title", {}).get("romaji", "Unknown Title")
        title_english = anilist.get("title", {}).get("english") or title_romaji
        episode = best.get("episode") or 1
        from_sec = int(best.get("from", 0))
        to_sec = int(best.get("to", 0))
        video_preview = best.get("video")
        is_adult = anilist.get("isAdult", False)

        m1, s1 = divmod(from_sec, 60)
        m2, s2 = divmod(to_sec, 60)
        timestamp = f"{m1:02d}:{s1:02d} - {m2:02d}:{s2:02d}"

        rating_badge = "🔞 NSFW / 18+" if is_adult else "🟢 PG"

        report = (
            f"🎬 <b>{title_english}</b>\n"
            f"🇯🇵 <i>{title_romaji}</i>\n\n"
            f"📺 <b>Episode:</b> <code>#{episode}</code>\n"
            f"⏱ <b>Timestamp:</b> <code>{timestamp}</code>\n"
            f"🎯 <b>Match Accuracy:</b> <code>{similarity:.1f}%</code>\n"
            f"🏷 <b>Rating:</b> {rating_badge}"
        )

        target_chat = m.chat_id or getattr(m.chat, "id", None)
        if video_preview and similarity >= 80:
            await c.send_file(
                target_chat,
                video_preview,
                caption=report,
                reply_to=reply.id,
            )
            await msg.delete()
        else:
            await msg.edit_msg(report)

    except Exception as e:
        await msg.edit_msg(f"❌ Anime trace error: <code>{e}</code>")
    finally:
        if input_file and os.path.exists(input_file):
            try:
                os.remove(input_file)
            except Exception:
                pass
